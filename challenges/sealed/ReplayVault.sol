// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract ReplayVault {
    address public signer;
    mapping(address => uint256) public balances;

    constructor(address signer_) {
        signer = signer_;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "no balance");
        balances[msg.sender] = 0;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function claim(uint256 amount, uint8 v, bytes32 r, bytes32 s) external {
        bytes32 digest = keccak256(abi.encodePacked(amount));
        require(ecrecover(digest, v, r, s) == signer, "bad sig");
        require(address(this).balance >= amount, "empty");
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
