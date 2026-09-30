// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title SafeNaiveFeeVault
/// @notice Patched twin — only owner may collect the fee.
contract SafeNaiveFeeVault {
    uint256 public constant FEE = 1 ether;
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function deposit() external payable {}

    function flashFee() external {
        require(msg.sender == owner, "not owner");
        require(address(this).balance >= FEE, "insufficient");
        (bool success, ) = msg.sender.call{value: FEE}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
