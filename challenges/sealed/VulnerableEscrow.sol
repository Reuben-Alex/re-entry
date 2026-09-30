// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract VulnerableEscrow {
    mapping(address => uint256) public locked;

    function deposit() external payable {
        locked[msg.sender] += msg.value;
    }

    function release(address beneficiary) external {
        uint256 amount = locked[beneficiary];
        require(amount > 0, "empty");
        locked[beneficiary] = 0;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
