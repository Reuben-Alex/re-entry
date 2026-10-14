// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract Logic {
    address public owner;
    mapping(address => uint256) public balances;

    function initialize() external {
        owner = msg.sender;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdrawAll() external {
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

contract Proxy {
    bytes32 private constant IMPL_SLOT =
        bytes32(uint256(keccak256("reentry.proxy.impl")) - 1);

    constructor(address impl) {
        bytes32 slot = IMPL_SLOT;
        assembly {
            sstore(slot, impl)
        }
    }

    function implementation() external view returns (address impl) {
        bytes32 slot = IMPL_SLOT;
        assembly {
            impl := sload(slot)
        }
    }

    fallback() external payable {
        bytes32 slot = IMPL_SLOT;
        assembly {
            let impl := sload(slot)
            calldatacopy(0, 0, calldatasize())
            let result := delegatecall(gas(), impl, 0, calldatasize(), 0, 0)
            returndatacopy(0, 0, returndatasize())
            switch result
            case 0 { revert(0, returndatasize()) }
            default { return(0, returndatasize()) }
        }
    }
}
