// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title VulnerableBlind
/// @notice Held-out demo target: missing access control on changeOwner().
///         Distinct from Treasury (no public withdrawAll without ownership)
///         and from Vault reentrancy — Attacker.sol fallback will not drain this.
///
/// BUG: anyone can call changeOwner(), then withdrawAll() as the new owner.
/// Canonical fix: Ownable-style onlyOwner on changeOwner (OpenZeppelin Ownable).
contract VulnerableBlind {
    address public owner;
    mapping(address => uint256) public balances;

    constructor() {
        owner = msg.sender;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    /// BUG: no access control — any caller can seize ownership.
    function changeOwner(address newOwner) external {
        owner = newOwner;
    }

    function withdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "no balance");
        balances[msg.sender] = 0;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function withdrawAll() external {
        require(msg.sender == owner, "not owner");
        uint256 amount = address(this).balance;
        require(amount > 0, "empty");
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
