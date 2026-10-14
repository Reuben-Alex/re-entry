// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract InflatingVault {
    uint256 public totalShares;
    uint256 public totalAssets;
    mapping(address => uint256) public shares;

    function deposit() external payable {
        require(msg.value > 0, "zero");
        uint256 minted;
        if (totalShares == 0) {
            minted = msg.value;
        } else {
            minted = (msg.value * totalShares) / totalAssets;
        }
        shares[msg.sender] += minted;
        totalShares += minted;
        totalAssets += msg.value;
    }

    function donate() external payable {
        totalAssets += msg.value;
    }

    function withdraw() external {
        uint256 userShares = shares[msg.sender];
        require(userShares > 0, "no shares");
        uint256 assets = (userShares * totalAssets) / totalShares;
        shares[msg.sender] = 0;
        totalShares -= userShares;
        totalAssets -= assets;
        (bool success, ) = msg.sender.call{value: assets}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
