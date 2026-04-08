// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import {BasisRating} from "src/BasisRating.sol";

contract DeployRating is Script {
    function run() external {
        string memory baseURI = vm.envOr("SBT_BASE_URI", string("https://basisprotocol.xyz/api/reports/sbt/"));

        vm.startBroadcast();
        BasisRating sbt = new BasisRating(baseURI);
        vm.stopBroadcast();

        console.log("BasisRating deployed to:", address(sbt));
        console.log("Keeper:", sbt.keeper());
        console.log("Base URI:", baseURI);
    }
}
