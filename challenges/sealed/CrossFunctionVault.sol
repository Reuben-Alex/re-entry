// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract CrossFunctionVault {
    mapping(address => uint256) public balances;
    bool private entered;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function transfer(address to, uint256 amount) external {
        require(balances[msg.sender] >= amount, "insufficient");
        balances[msg.sender] -= amount;
        balances[to] += amount;
    }

    function withdraw() external {
        require(!entered, "reenter");
        entered = true;
        uint256 amount = balances[msg.sender];
        require(amount > 0, "no balance");
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
        balances[msg.sender] = 0;
        entered = false;
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
