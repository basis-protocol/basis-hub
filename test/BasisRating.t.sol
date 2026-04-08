// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {BasisRating} from "../src/BasisRating.sol";

contract BasisRatingTest is Test {
    BasisRating public sbt;

    address public keeper = address(this);
    address public recipient = address(0xBEEF);
    address public nonKeeper = address(0xDEAD);

    string public constant BASE_URI = "https://basisprotocol.xyz/api/reports/sbt/";

    function setUp() public {
        sbt = new BasisRating(BASE_URI);
    }

    // ═══════════════════════════════════════════════════════════
    // CONSTRUCTOR
    // ═══════════════════════════════════════════════════════════

    function test_Constructor_SetsKeeper() public view {
        assertEq(sbt.keeper(), keeper);
    }

    function test_Constructor_SetsBaseURI() public view {
        assertEq(sbt.baseURI(), BASE_URI);
    }

    function test_Constructor_NameAndSymbol() public view {
        assertEq(sbt.name(), "Basis Rating");
        assertEq(sbt.symbol(), "BRATE");
    }

    // ═══════════════════════════════════════════════════════════
    // MINT
    // ═══════════════════════════════════════════════════════════

    function test_MintRating_CreatesToken() public {
        bytes32 entityId = keccak256("usdc");
        bytes32 reportHash = bytes32(uint256(0xABCD));

        uint256 tokenId = sbt.mintRating(
            recipient, entityId, 0, 8750, bytes2("A "), 2, reportHash, 100
        );

        assertEq(tokenId, 0);
        assertEq(sbt.ownerOf(0), recipient);
    }

    function test_MintRating_StoresRatingStruct() public {
        bytes32 entityId = keccak256("usdc");
        bytes32 reportHash = bytes32(uint256(0x1234));

        sbt.mintRating(recipient, entityId, 0, 8750, bytes2("A "), 2, reportHash, 100);

        (
            bytes32 eid, uint8 etype, uint16 score, bytes2 grade,
            uint8 conf, bytes32 rh, uint48 ts, uint16 mv
        ) = sbt.ratings(0);

        assertEq(eid, entityId);
        assertEq(etype, 0);
        assertEq(score, 8750);
        assertEq(grade, bytes2("A "));
        assertEq(conf, 2);
        assertEq(rh, reportHash);
        assertEq(ts, uint48(block.timestamp));
        assertEq(mv, 100);
    }

    function test_MintRating_SetsEntityToToken() public {
        bytes32 entityId = keccak256("aave");
        sbt.mintRating(recipient, entityId, 1, 7200, bytes2("B+"), 1, bytes32(0), 100);

        assertEq(sbt.entityToToken(entityId), 0);
    }

    function test_MintRating_IncrementsTokenId() public {
        bytes32 id1 = keccak256("usdc");
        bytes32 id2 = keccak256("usdt");

        uint256 t1 = sbt.mintRating(recipient, id1, 0, 9000, bytes2("A+"), 2, bytes32(0), 100);
        uint256 t2 = sbt.mintRating(recipient, id2, 0, 8500, bytes2("A "), 2, bytes32(0), 100);

        assertEq(t1, 0);
        assertEq(t2, 1);
    }

    function test_MintRating_RevertsNonKeeper() public {
        vm.prank(nonKeeper);
        vm.expectRevert(BasisRating.NotKeeper.selector);
        sbt.mintRating(recipient, keccak256("usdc"), 0, 8750, bytes2("A "), 2, bytes32(0), 100);
    }

    // ═══════════════════════════════════════════════════════════
    // SOULBOUND — transfer reverts
    // ═══════════════════════════════════════════════════════════

    function test_Transfer_Reverts() public {
        sbt.mintRating(recipient, keccak256("usdc"), 0, 8750, bytes2("A "), 2, bytes32(0), 100);

        vm.prank(recipient);
        vm.expectRevert("Soulbound: non-transferable");
        sbt.transferFrom(recipient, nonKeeper, 0);
    }

    function test_SafeTransfer_Reverts() public {
        sbt.mintRating(recipient, keccak256("usdc"), 0, 8750, bytes2("A "), 2, bytes32(0), 100);

        vm.prank(recipient);
        vm.expectRevert("Soulbound: non-transferable");
        sbt.safeTransferFrom(recipient, nonKeeper, 0);
    }

    // ═══════════════════════════════════════════════════════════
    // UPDATE RATING
    // ═══════════════════════════════════════════════════════════

    function test_UpdateRating_UpdatesFields() public {
        sbt.mintRating(recipient, keccak256("usdc"), 0, 8750, bytes2("A "), 2, bytes32(0), 100);

        bytes32 newHash = bytes32(uint256(0x5678));
        sbt.updateRating(0, 9100, bytes2("A+"), 2, newHash, 110);

        (, , uint16 score, bytes2 grade, , bytes32 rh, , uint16 mv) = sbt.ratings(0);
        assertEq(score, 9100);
        assertEq(grade, bytes2("A+"));
        assertEq(rh, newHash);
        assertEq(mv, 110);
    }

    function test_UpdateRating_RevertsNonKeeper() public {
        sbt.mintRating(recipient, keccak256("usdc"), 0, 8750, bytes2("A "), 2, bytes32(0), 100);

        vm.prank(nonKeeper);
        vm.expectRevert(BasisRating.NotKeeper.selector);
        sbt.updateRating(0, 9000, bytes2("A+"), 2, bytes32(0), 100);
    }

    function test_UpdateRating_RevertsNonExistent() public {
        vm.expectRevert("Token does not exist");
        sbt.updateRating(999, 9000, bytes2("A+"), 2, bytes32(0), 100);
    }

    // ═══════════════════════════════════════════════════════════
    // TOKEN URI
    // ═══════════════════════════════════════════════════════════

    function test_TokenURI_ReturnsCorrectURI() public {
        sbt.mintRating(recipient, keccak256("usdc"), 0, 8750, bytes2("A "), 2, bytes32(0), 100);
        assertEq(sbt.tokenURI(0), string(abi.encodePacked(BASE_URI, "0")));
    }

    function test_TokenURI_MultiDigit() public {
        // Mint 11 tokens
        for (uint256 i = 0; i < 11; i++) {
            sbt.mintRating(recipient, keccak256(abi.encodePacked("token", i)), 0, 8000, bytes2("A-"), 2, bytes32(0), 100);
        }
        assertEq(sbt.tokenURI(10), string(abi.encodePacked(BASE_URI, "10")));
    }

    function test_TokenURI_RevertsNonExistent() public {
        vm.expectRevert("Token does not exist");
        sbt.tokenURI(999);
    }

    // ═══════════════════════════════════════════════════════════
    // SET BASE URI
    // ═══════════════════════════════════════════════════════════

    function test_SetBaseURI_Updates() public {
        string memory newURI = "https://new.basisprotocol.xyz/sbt/";
        sbt.setBaseURI(newURI);
        assertEq(sbt.baseURI(), newURI);
    }

    function test_SetBaseURI_RevertsNonKeeper() public {
        vm.prank(nonKeeper);
        vm.expectRevert(BasisRating.NotKeeper.selector);
        sbt.setBaseURI("https://evil.com/");
    }
}
