// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title NaiveFeeVault
/// @notice Educational miniature inspired by Damn Vulnerable DeFi
///         "Naive receiver" (MIT). Rewritten for Re-entry — see
///         benchmarks/THIRD_PARTY_LICENSES.md.
///
/// BUG: anyone can call flashFee() and pull a fixed FEE from the vault
/// to msg.sender (no borrower authorization).
contract NaiveFeeVault {
    uint256 public constant FEE = 1 ether;

    function deposit() external payable {}

    /// Permissionless fee pull — the vulnerability.
    function flashFee() external {
        require(address(this).balance >= FEE, "insufficient");
        (bool success, ) = msg.sender.call{value: FEE}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
