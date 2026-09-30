// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract VulnerableTreasury {
    address public owner;
    uint256 public totalDeposits;

    constructor() {
        owner = msg.sender;
    }

    function deposit() external payable {
        totalDeposits += msg.value;
    }

    function withdrawAll() external {
        uint256 amount = address(this).balance;
        require(amount > 0, "empty");
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
