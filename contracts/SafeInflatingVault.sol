// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title SafeInflatingVault
/// @notice Patched twin. Deposits that would round to zero shares are rejected,
///         and donations do not change the share price.
contract SafeInflatingVault {
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
        require(minted > 0, "zero shares");
        shares[msg.sender] += minted;
        totalShares += minted;
        totalAssets += msg.value;
    }

    function donate() external payable {}

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
