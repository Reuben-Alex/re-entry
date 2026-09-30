// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title VulnerableOracleVault
/// @notice Spot-price oracle anyone can overwrite (oracle manipulation demo).
/// Deposit shares at price=1e18, setPrice(higher), withdraw more ETH than deposited.
contract VulnerableOracleVault {
    uint256 public price = 1 ether;
    mapping(address => uint256) public shares;

    function deposit() external payable {
        require(msg.value > 0, "zero");
        // mint shares 1:1 at current price units
        shares[msg.sender] += msg.value;
    }

    /// BUG: unrestricted oracle update (OWASP-style oracle manipulation).
    function setPrice(uint256 newPrice) external {
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
