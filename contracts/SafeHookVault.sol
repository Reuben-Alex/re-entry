// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

interface ITokenHook {
    function tokensReceived(address from, uint256 amount) external;
}

contract NotifyToken {
    mapping(address => uint256) public balanceOf;

    function mintAndNotify(address to, uint256 amount) external {
        balanceOf[to] += amount;
        if (to.code.length > 0) {
            ITokenHook(to).tokensReceived(msg.sender, amount);
        }
    }
}

/// @title SafeHookVault
/// @notice Patched twin. Bookkeeping is updated before the token hook and the ETH send.
contract SafeHookVault {
    NotifyToken public notify;
    mapping(address => uint256) public balances;

    constructor(address notifyToken) {
        notify = NotifyToken(notifyToken);
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "no balance");
        balances[msg.sender] = 0;
        notify.mintAndNotify(msg.sender, amount);
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
