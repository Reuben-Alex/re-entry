// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title SafeTreasury
/// @notice Patched twin of VulnerableTreasury with owner-only withdrawAll().
contract SafeTreasury {
    address public owner;
    uint256 public totalDeposits;

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    function deposit() external payable {
        totalDeposits += msg.value;
    }

    function withdrawAll() external onlyOwner {
        uint256 amount = address(this).balance;
        require(amount > 0, "empty");
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
