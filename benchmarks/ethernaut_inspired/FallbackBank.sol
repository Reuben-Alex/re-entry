// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title FallbackBank
/// @notice Educational miniature inspired by OpenZeppelin Ethernaut "Fallback"
///         (MIT). Rewritten for the Re-entry sandbox — not a copy of production
///         Ethernaut bytecode. See benchmarks/THIRD_PARTY_LICENSES.md.
///
/// BUG: sending ETH via receive() after any contribute() seizes ownership,
/// then withdraw() drains the bank.
contract FallbackBank {
    mapping(address => uint256) public contributions;
    address public owner;

    constructor() {
        owner = msg.sender;
        contributions[msg.sender] = 1000 * (1 ether);
    }

    /// Used by the deploy script to fund the challenge.
    function deposit() external payable {}

    function contribute() external payable {
        require(msg.value > 0, "need value");
        contributions[msg.sender] += msg.value;
    }

    receive() external payable {
        require(msg.value > 0 && contributions[msg.sender] > 0, "no contrib");
        owner = msg.sender;
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
