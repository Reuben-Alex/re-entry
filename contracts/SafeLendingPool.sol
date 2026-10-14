// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

interface IFlashBorrower {
    function onFlashLoan(uint256 amount) external;
}

contract CollateralToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor() {
        balanceOf[msg.sender] = 10 ether;
    }

    function approve(address spender, uint256 amount) external {
        allowance[msg.sender][spender] = amount;
    }

    function transfer(address to, uint256 amount) external {
        require(balanceOf[msg.sender] >= amount, "bal");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
    }

    function transferFrom(address from, address to, uint256 amount) external {
        require(allowance[from][msg.sender] >= amount, "allow");
        allowance[from][msg.sender] -= amount;
        require(balanceOf[from] >= amount, "bal");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
    }
}

contract MiniAMM {
    CollateralToken public token;
    uint256 public ethReserve;
    uint256 public tokenReserve;

    constructor(address token_) {
        token = CollateralToken(token_);
    }

    function seed(uint256 tokenAmount) external payable {
        token.transferFrom(msg.sender, address(this), tokenAmount);
        ethReserve += msg.value;
        tokenReserve += tokenAmount;
    }

    function tokenPrice() public view returns (uint256) {
        return 1 ether;
    }

    function swapExactEth() external payable returns (uint256 outAmount) {
        require(msg.value > 0, "zero");
        uint256 newEth = ethReserve + msg.value;
        uint256 newToken = (ethReserve * tokenReserve) / newEth;
        outAmount = tokenReserve - newToken;
        ethReserve = newEth;
        tokenReserve = newToken;
        token.transfer(msg.sender, outAmount);
    }

    function swapExactToken(uint256 amountIn) external returns (uint256 ethOut) {
        token.transferFrom(msg.sender, address(this), amountIn);
        uint256 newToken = tokenReserve + amountIn;
        uint256 newEth = (ethReserve * tokenReserve) / newToken;
        ethOut = ethReserve - newEth;
        tokenReserve = newToken;
        ethReserve = newEth;
        (bool success, ) = msg.sender.call{value: ethOut}("");
        require(success, "eth");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}

contract FlashLender {
    function flash(uint256 amount) external {
        uint256 beforeBalance = address(this).balance;
        require(beforeBalance >= amount, "liq");
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "send");
        IFlashBorrower(msg.sender).onFlashLoan(amount);
        require(address(this).balance >= beforeBalance, "repay");
    }

    function fund() external payable {}

    receive() external payable {}

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}

/// @title SafeLendingPool
/// @notice Patched twin. Borrow value uses a fixed price, so a same-transaction
///         reserve move cannot inflate credit.
contract SafeLendingPool {
    MiniAMM public amm;
    CollateralToken public token;
    FlashLender public flashLender;
    mapping(address => uint256) public collateral;

    constructor(address amm_, address token_, address payable flash_) {
        amm = MiniAMM(amm_);
        token = CollateralToken(token_);
        flashLender = FlashLender(flash_);
    }

    function deposit() external payable {}

    function depositCollateral(uint256 amount) external {
        token.transferFrom(msg.sender, address(this), amount);
        collateral[msg.sender] += amount;
    }

    function borrow() external {
        uint256 value = collateral[msg.sender];
        require(value > 0, "zero");
        uint256 pay = value;
        if (pay > address(this).balance) {
            pay = address(this).balance;
        }
        require(pay > 0, "empty");
        collateral[msg.sender] = 0;
        (bool success, ) = msg.sender.call{value: pay}("");
        require(success, "borrow");
    }

    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
