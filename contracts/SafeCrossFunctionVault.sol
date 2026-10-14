// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title SafeCrossFunctionVault
/// @notice Patched twin. Balance is cleared before the external call, and
///         transfer shares the same lock.
contract SafeCrossFunctionVault {
    mapping(address => uint256) public balances;
    bool private entered;

    modifier locked() {
        require(!entered, "reenter");
        entered = true;
        _;
        entered = false;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function transfer(address to, uint256 amount) external locked {
        require(balances[msg.sender] >= amount, "insufficient");
        balances[msg.sender] -= amount;
        balances[to] += amount;
    }

    function withdraw() external locked {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "no balance");
        balances[msg.sender] = 0;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
