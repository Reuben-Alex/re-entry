"""
Export agent-generated exploits as Foundry test files.
"""
from orchestrator.proposer import ExploitProposal


def export_foundry_poc(
    target_name: str,
    target_address: str,
    proposal: ExploitProposal,
) -> str:
    """Build a Foundry test file wrapping the generated exploit contract."""
    exploit_source = proposal.solidity_source.strip()
    contract_name = proposal.contract_name
    entry_fn = proposal.entry_function
    value_wei = proposal.entry_value_wei

    return f"""// SPDX-License-Identifier: MIT
// Re-entry Foundry export — {target_name}
pragma solidity ^0.8.19;

import "forge-std/Test.sol";

{exploit_source}

contract ExploitTest is Test {{
    address constant TARGET = {target_address};
    {contract_name} attacker;

    function setUp() public {{
        vm.deal(address(this), 10 ether);
        attacker = new {contract_name}(TARGET);
    }}

    function test_exploit_drains_target() public {{
        uint256 before = TARGET.balance;
        require(before > 0, "target must be funded before running PoC");
        attacker.{entry_fn}{{value: {value_wei}}}();
        uint256 after = TARGET.balance;
        assertLt(after, before, "exploit did not reduce target balance");
    }}
}}
"""
