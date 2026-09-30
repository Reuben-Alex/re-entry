// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title SafeOracleVault
/// @notice Patched twin — onlyOwner may update the price oracle.
contract SafeOracleVault {
    uint256 public price = 1 ether;
    mapping(address => uint256) public shares;
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function deposit() external payable {
        require(msg.value > 0, "zero");
        shares[msg.sender] += msg.value;
    }

    function setPrice(uint256 newPrice) external {
        require(msg.sender == owner, "not owner");
        require(newPrice > 0, "bad price");
        price = newPrice;
    }

    function withdraw() external {
        uint256 userShares = shares[msg.sender];
        require(userShares > 0, "no shares");
        uint256 amount = (userShares * price) / 1 ether;
        shares[msg.sender] = 0;
        require(address(this).balance >= amount, "insolvent");
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
