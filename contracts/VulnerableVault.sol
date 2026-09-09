// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title VulnerableVault
/// @notice DELIBERATELY BUGGY demo contract, modeled in miniature on the
///         classic 2016 DAO-hack reentrancy pattern. This is the target
///         PoCForge's agent is expected to find and drain.
///
/// WHAT THIS CONTRACT DOES (in plain terms):
///   Anyone can deposit ETH. Anyone can withdraw whatever they deposited.
///   That's it. A completely normal-looking savings vault.
///
/// THE BUG (this is the part that matters):
///   Solidity functions run top to bottom, one line at a time, and an
///   external call (line marked below) can trigger code in ANOTHER
///   contract before this function finishes. If that other contract calls
///   back into withdraw() before this function reaches the line that
///   zeroes the balance, it can withdraw the same balance again. And
///   again. That's "reentrancy" — the function re-enters itself before
///   its own bookkeeping is done.
contract VulnerableVault {
    // A simple ledger: which address deposited how much ETH (in wei).
    mapping(address => uint256) public balances;

    /// Anyone can call this and send ETH along with the call.
    /// `msg.value` is however much ETH was attached to the transaction.
    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    /// THE VULNERABLE FUNCTION.
    function withdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "no balance");

        // --- BUG IS HERE ---
        // This line sends ETH to msg.sender. If msg.sender is a CONTRACT
        // (not a normal wallet), sending it ETH automatically triggers
        // that contract's receive() function, and execution jumps there
        // BEFORE this withdraw() function continues to the next line.
        //
        // If the receiving contract's receive() calls withdraw() again,
        // `balances[msg.sender]` is STILL the old, un-zeroed amount,
        // because we haven't reached the line below yet. It withdraws
        // the same funds again. This can repeat until the vault is
        // empty or the call stack runs out (Solidity's default limit
        // is ~1024 deep, plenty for a real drain).
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");

        // This line — the fix — only runs AFTER the reentrant calls
        // above have already drained the vault.
        balances[msg.sender] = 0;
    }

    /// Convenience view function so the Python orchestrator can check
    /// the vault's total ETH balance before/after an attack.
    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}

// -----------------------------------------------------------------------
// THE FIX (for reference — see SafeVault.sol for the corrected version):
// Simply reorder the two lines above so the balance is zeroed BEFORE
// the external call. This is the standard "checks-effects-interactions"
// pattern: check conditions, update your own state, THEN talk to the
// outside world. Once state is already zeroed, a reentrant call sees
// balance = 0 and its own `require(amount > 0)` fails, stopping the loop.
// -----------------------------------------------------------------------
