// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title SafeFallbackBank
/// @notice Patched twin — receive() no longer transfers ownership.
contract SafeFallbackBank {
    mapping(address => uint256) public contributions;
    address public owner;

    constructor() {
        owner = msg.sender;
        contributions[msg.sender] = 1000 * (1 ether);
    }

    function deposit() external payable {}

    function contribute() external payable {
        require(msg.value > 0, "need value");
        contributions[msg.sender] += msg.value;
    }

    receive() external payable {
        require(msg.value > 0, "need value");
        contributions[msg.sender] += msg.value;
    }

    function withdraw() external {
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
