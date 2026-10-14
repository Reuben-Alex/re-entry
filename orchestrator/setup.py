"""
Deploy manifest targets from their setup spec.

Companions deploy first. Constructor args that name a companion are
replaced with that companion's address. The primary address is what the
agent attacks.
"""
import json
from pathlib import Path

from eth_account import Account
from web3 import Web3

from orchestrator import challenges, config
from orchestrator.chain import compile_source_map, deploy

ONE_ETH = 10**18
EPHEMERAL_SIGNER = "__ephemeral_signer__"
DEPLOYED_PATH = Path(config.PROJECT_ROOT) / "deployed_contracts.json"


def _as_int(value) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        return int(value, 16) if value.startswith("0x") else int(value)
    return int(value)


def merged_setup(target: challenges.ChallengeTarget) -> dict:
    """Fill defaults so older manifest entries keep the single-vault flow."""
    setup = {
        "fund": {
            "fn": "deposit",
            "amount_wei": ONE_ETH,
            "accounts": [1, 2, 3],
        },
        "preflight_min_wei": ONE_ETH,
        "companions": [],
        "constructor_args": [],
        "after_deploy": [],
        "after_attack": [],
        "benign": None,
        "schedule_note": "",
        "tokens": [],
        "abi_contract": None,
        "observation": None,
        "observation_amount_wei": ONE_ETH,
    }
    custom = dict(target.setup or {})
    if "fund" in custom:
        setup["fund"] = custom["fund"]
    for key in (
        "preflight_min_wei",
        "companions",
        "constructor_args",
        "after_deploy",
        "after_attack",
        "benign",
        "schedule_note",
        "tokens",
        "abi_contract",
        "observation",
        "observation_amount_wei",
    ):
        if key in custom:
            setup[key] = custom[key]
    if setup["fund"] is None and "preflight_min_wei" not in custom:
        setup["preflight_min_wei"] = 0
    return setup


def _input_types(fn_abi: dict) -> list[str]:
    return [item.get("type", "") for item in fn_abi.get("inputs", [])]


def default_benign(abi: list) -> list[dict]:
    """Deposit, then an honest withdraw when the ABI has one."""
    names = {}
    for entry in abi:
        if entry.get("type") == "function" and entry.get("name"):
            names[entry["name"]] = entry
    steps = []
    if "deposit" in names and _input_types(names["deposit"]) == []:
        steps.append(
            {"fn": "deposit", "value_wei": str(ONE_ETH), "from_account": 1}
        )
    if "withdraw" in names and _input_types(names["withdraw"]) == []:
        steps.append({"fn": "withdraw", "from_account": 1})
    elif "withdrawAll" in names and _input_types(names["withdrawAll"]) == []:
        steps.append({"fn": "withdrawAll", "from_account": 0})
    return steps


def _resolve_arg(arg, addresses: dict, w3, signer_address: str):
    if arg == EPHEMERAL_SIGNER:
        return signer_address
    if isinstance(arg, str) and arg.startswith("account:"):
        return w3.eth.accounts[int(arg.split(":", 1)[1])]
    if isinstance(arg, str) and arg in addresses:
        return addresses[arg]
    if isinstance(arg, str) and arg.isdigit():
        return int(arg)
    return arg


def _call_step(w3, contract, step: dict, addresses: dict, signer_address: str) -> None:
    sender = w3.eth.accounts[int(step.get("from_account", 0))]
    args = [
        _resolve_arg(arg, addresses, w3, signer_address)
        for arg in (step.get("args") or [])
    ]
    value = _as_int(step.get("value_wei", 0))
    tx_hash = contract.functions[step["fn"]](*args).transact(
        {"from": sender, "value": value}
    )
    w3.eth.wait_for_transaction_receipt(tx_hash)


def _contract_for(w3, step: dict, primary, abis: dict, addresses: dict):
    target = step.get("on", "target")
    if target in ("target", "primary"):
        return primary
    return w3.eth.contract(address=addresses[target], abi=abis[target])


def _run_steps(w3, steps: list, primary, abis, addresses, signer_address: str) -> None:
    for step in steps:
        contract = _contract_for(w3, step, primary, abis, addresses)
        _call_step(w3, contract, step, addresses, signer_address)


def _observation(setup: dict, signer) -> dict:
    if setup.get("observation") != "replay_signature":
        return {}
    amount = _as_int(setup.get("observation_amount_wei", ONE_ETH))
    digest = Web3.solidity_keccak(["uint256"], [amount])
    signed = Account._sign_hash(digest, private_key=signer.key)
    return {
        "note": (
            "Observed authorization over one uint256 amount. "
            "It is not bound to a caller."
        ),
        "amount_wei": str(amount),
        "v": signed.v,
        "r": "0x" + signed.r.to_bytes(32, "big").hex(),
        "s": "0x" + signed.s.to_bytes(32, "big").hex(),
    }


def _deploy_from_map(
    w3,
    compiled: dict,
    setup: dict,
    primary_name: str,
    deployer: str,
    signer,
) -> tuple:
    """Deploy companions and the primary contract. Returns call contract and maps."""
    addresses = {}
    abis = {}
    for companion in setup.get("companions") or []:
        name = companion["contract_name"]
        abi, bytecode = compiled[name]
        args = [
            _resolve_arg(arg, addresses, w3, signer.address)
            for arg in (companion.get("args") or [])
        ]
        contract = deploy(w3, abi, bytecode, deployer, args)
        addresses[name] = contract.address
        abis[name] = abi

    abi, bytecode = compiled[primary_name]
    constructor_args = [
        _resolve_arg(arg, addresses, w3, signer.address)
        for arg in (setup.get("constructor_args") or [])
    ]
    primary = deploy(w3, abi, bytecode, deployer, constructor_args)
    addresses[primary_name] = primary.address
    abis[primary_name] = abi

    abi_name = setup.get("abi_contract") or primary_name
    call_abi = compiled[abi_name][0]
    callable_contract = w3.eth.contract(address=primary.address, abi=call_abi)
    return callable_contract, addresses, abis, call_abi


def _fund(w3, contract, setup: dict, addresses: dict, signer_address: str) -> None:
    fund = setup.get("fund")
    if not fund:
        return
    amount = _as_int(fund.get("amount_wei", ONE_ETH))
    for index in fund.get("accounts", [1, 2, 3]):
        _call_step(
            w3,
            contract,
            {
                "fn": fund.get("fn", "deposit"),
                "value_wei": amount,
                "from_account": index,
                "args": fund.get("args") or [],
            },
            addresses,
            signer_address,
        )


def deploy_target(w3, target: challenges.ChallengeTarget, deployer: str) -> dict:
    """Deploy one manifest target. Returns the deployed_contracts.json entry."""
    source_path = challenges.resolve_source_path(target)
    compiled = compile_source_map(source_path.read_text())
    setup = merged_setup(target)
    signer = Account.create()
    primary_name = target.solidity_contract_name
    contract, addresses, abis, call_abi = _deploy_from_map(
        w3, compiled, setup, primary_name, deployer, signer
    )
    _run_steps(
        w3,
        setup.get("after_deploy") or [],
        contract,
        abis,
        addresses,
        signer.address,
    )
    _fund(w3, contract, setup, addresses, signer.address)

    benign = setup.get("benign")
    if benign is None:
        benign = default_benign(call_abi)

    plan_args = []
    for arg in setup.get("constructor_args") or []:
        if arg == EPHEMERAL_SIGNER:
            plan_args.append(signer.address)
        else:
            plan_args.append(arg)

    context = {
        "addresses": addresses,
        "abis": abis,
        "tokens": {
            name: addresses[name]
            for name in (setup.get("tokens") or [])
            if name in addresses
        },
        "after_attack": setup.get("after_attack") or [],
        "benign": benign,
        "schedule_note": setup.get("schedule_note") or "",
        "observations": _observation(setup, signer),
        "preflight_min_wei": _as_int(setup.get("preflight_min_wei", ONE_ETH)),
        "deploy_plan": {
            "source": str(source_path.relative_to(config.PROJECT_ROOT)),
            "companions": setup.get("companions") or [],
            "primary": primary_name,
            "constructor_args": plan_args,
            "abi_contract": setup.get("abi_contract") or primary_name,
            "after_deploy": setup.get("after_deploy") or [],
            "fund": setup.get("fund"),
            "benign": benign,
            "signer": signer.address,
        },
    }
    return {"address": contract.address, "abi": call_abi, "context": context}


def redeploy_from_source(w3, source: str, plan: dict, deployer: str):
    """
    Deploy a patched copy of a target using the saved deploy plan.

    Returns the web3 contract at the primary address, using the call ABI.
    """
    compiled = compile_source_map(source)
    signer_address = plan.get("signer") or deployer
    signer = type("Signer", (), {"address": signer_address, "key": b""})()
    setup = {
        "companions": plan.get("companions") or [],
        "constructor_args": plan.get("constructor_args") or [],
        "abi_contract": plan.get("abi_contract"),
        "after_deploy": plan.get("after_deploy") or [],
        "fund": plan.get("fund"),
    }
    contract, addresses, abis, _call_abi = _deploy_from_map(
        w3, compiled, setup, plan["primary"], deployer, signer
    )
    _run_steps(w3, setup["after_deploy"], contract, abis, addresses, signer_address)
    _fund(w3, contract, setup, addresses, signer_address)
    return contract


def attach_context(sandbox, deployed_entry: dict) -> None:
    """Stash deploy context on the sandbox for the executor and patch check."""
    sandbox.run_context = deployed_entry.get("context") or {}


def deploy_all(w3=None) -> dict:
    """Deploy every manifest target and write deployed_contracts.json."""
    from orchestrator.chain import get_web3

    if w3 is None:
        w3 = get_web3(config.LOCAL_RPC_URL)
    deployer = w3.eth.accounts[0]
    deployed = {}
    for target in challenges.list_deployable():
        try:
            challenges.resolve_source_path(target)
        except FileNotFoundError as exc:
            if target.tier == "held_out_live":
                print(f"Skipping {target.name} — {exc}")
                continue
            raise
        entry = deploy_target(w3, target, deployer)
        balance = w3.eth.get_balance(entry["address"])
        print(
            f"Deployed {target.name} at {entry['address']} "
            f"({w3.from_wei(balance, 'ether')} ETH)"
        )
        deployed[target.name] = entry

    DEPLOYED_PATH.write_text(json.dumps(deployed, indent=2))
    print(f"\nWrote {DEPLOYED_PATH}")
    return deployed


def format_sandbox_notes(context: dict | None) -> str:
    """Text block passed to Ultra. Empty when the target has no schedule."""
    if not context:
        return ""
    parts = []
    note = (context.get("schedule_note") or "").strip()
    if note:
        parts.append(note)
    observations = context.get("observations") or {}
    if observations:
        parts.append(
            "SANDBOX OBSERVATIONS:\n" + json.dumps(observations, indent=2)
        )
    return "\n\n".join(parts)
