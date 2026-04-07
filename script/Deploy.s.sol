// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import {BasisOracle} from "src/BasisSIIOracle.sol";

contract DeployOracle is Script {
    function run() external {
        address keeperAddress = vm.envAddress("KEEPER_ADDRESS");
        vm.startBroadcast();
        BasisOracle oracle = new BasisOracle(keeperAddress);
        vm.stopBroadcast();
        console.log("Oracle deployed to:", address(oracle));
        console.log("Keeper:", keeperAddress);
        console.log("Owner:", oracle.owner());
    }
}
