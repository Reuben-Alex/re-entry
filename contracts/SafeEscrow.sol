// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract SafeEscrow {
    mapping(address => uint256) public locked;

    function deposit() external payable {
        locked[msg.sender] += msg.value;
    }

    function release() external {
        uint256 amount = locked[msg.sender];
        require(amount > 0, "empty");
        locked[msg.sender] = 0;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
