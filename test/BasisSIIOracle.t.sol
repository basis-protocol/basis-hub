// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {BasisOracle} from "../src/BasisSIIOracle.sol";
import {IBasisSIIOracle} from "../src/interfaces/IBasisSIIOracle.sol";
import {BasisSafeGuard} from "../src/BasisSafeGuard.sol";

contract BasisOracleTest is Test {
    BasisOracle public oracle;
    BasisSafeGuard public guard;

    address public owner = address(this);
    address public keeper = address(0xBEEF);
    address public nonKeeper = address(0xDEAD);

    // Dummy token addresses
    address public usdc = address(0x1);
    address public usdt = address(0x2);
    address public dai = address(0x3);

    // Protocol addresses
    address public aavePool = address(0xA);
    address public driftVault = address(0xB);

    uint48 public baseTimestamp;

    function setUp() public {
        baseTimestamp = uint48(block.timestamp);
        oracle = new BasisOracle(keeper);
        guard = new BasisSafeGuard(address(oracle), 5000, 3600);
    }

    // ═══════════════════════════════════════════════════════════
    // CONSTRUCTOR TESTS
    // ═══════════════════════════════════════════════════════════

    function test_Constructor_SetsOwner() public {
        assertEq(oracle.owner(), owner);
    }

    function test_Constructor_SetsKeeper() public {
        assertEq(oracle.keeper(), keeper);
    }

    function test_Constructor_RevertsZeroKeeper() public {
        vm.expectRevert("Basis: zero keeper");
        new BasisOracle(address(0));
    }

    function test_Constructor_NotPaused() public {
        assertFalse(oracle.paused());
    }

    // ═══════════════════════════════════════════════════════════
    // SII — updateScore
    // ═══════════════════════════════════════════════════════════

    function test_UpdateScore_StoresCorrectly() public {
        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);

        (uint16 score, bytes2 grade, uint48 ts, uint16 ver) = oracle.getScore(usdc);
        assertEq(score, 8500);
        assertEq(grade, "A ");
        assertEq(ts, baseTimestamp);
        assertEq(ver, 1);
    }

    function test_UpdateScore_EmitsEvent() public {
        vm.expectEmit(true, false, false, true);
        emit IBasisSIIOracle.ScoreUpdated(usdc, 8500, "A ", baseTimestamp, 1);
        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);
    }

    function test_UpdateScore_RejectsNonKeeper() public {
        vm.prank(nonKeeper);
        vm.expectRevert("Basis: not keeper");
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);
    }

    function test_UpdateScore_RejectsZeroAddress() public {
        vm.prank(keeper);
        vm.expectRevert("Basis: zero address");
        oracle.updateScore(address(0), 8500, "A ", baseTimestamp, 1);
    }

    function test_UpdateScore_RejectsOverRange() public {
        vm.prank(keeper);
        vm.expectRevert("Basis: score out of range");
        oracle.updateScore(usdc, 10001, "A+", baseTimestamp, 1);
    }

    function test_UpdateScore_RejectsFutureTimestamp() public {
        vm.prank(keeper);
        vm.expectRevert("Basis: future timestamp");
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp + 1000, 1);
    }

    function test_UpdateScore_RejectsOldTimestamp() public {
        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);

        vm.prank(keeper);
        vm.expectRevert("Basis: stale update");
        oracle.updateScore(usdc, 8600, "A ", baseTimestamp, 1);
    }

    function test_UpdateScore_AcceptsNewerTimestamp() public {
        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);

        vm.warp(block.timestamp + 100);
        vm.prank(keeper);
        oracle.updateScore(usdc, 8600, "A ", baseTimestamp + 100, 1);

        (uint16 score,,,) = oracle.getScore(usdc);
        assertEq(score, 8600);
    }

    function test_UpdateScore_AcceptsMaxScore() public {
        vm.prank(keeper);
        oracle.updateScore(usdc, 10000, "A+", baseTimestamp, 1);

        (uint16 score,,,) = oracle.getScore(usdc);
        assertEq(score, 10000);
    }

    function test_UpdateScore_AcceptsZeroScore() public {
        vm.prank(keeper);
        oracle.updateScore(usdc, 0, "F ", baseTimestamp, 1);

        (uint16 score,,,) = oracle.getScore(usdc);
        assertEq(score, 0);
    }

    function test_UpdateScore_TracksTokenOnce() public {
        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);
        assertEq(oracle.getScoredTokenCount(), 1);

        vm.warp(block.timestamp + 100);
        vm.prank(keeper);
        oracle.updateScore(usdc, 8600, "A ", baseTimestamp + 100, 1);
        assertEq(oracle.getScoredTokenCount(), 1);
    }

    // ═══════════════════════════════════════════════════════════
    // SII — batchUpdateScores
    // ═══════════════════════════════════════════════════════════

    function test_BatchUpdateScores_Works() public {
        address[] memory tokens = new address[](2);
        tokens[0] = usdc;
        tokens[1] = usdt;

        uint16[] memory scores_ = new uint16[](2);
        scores_[0] = 8500;
        scores_[1] = 7200;

        bytes2[] memory grades = new bytes2[](2);
        grades[0] = "A ";
        grades[1] = "B ";

        uint48[] memory timestamps = new uint48[](2);
        timestamps[0] = baseTimestamp;
        timestamps[1] = baseTimestamp;

        uint16[] memory versions = new uint16[](2);
        versions[0] = 1;
        versions[1] = 1;

        vm.prank(keeper);
        oracle.batchUpdateScores(tokens, scores_, grades, timestamps, versions);

        (uint16 s1,,,) = oracle.getScore(usdc);
        (uint16 s2,,,) = oracle.getScore(usdt);
        assertEq(s1, 8500);
        assertEq(s2, 7200);
        assertEq(oracle.getScoredTokenCount(), 2);
    }

    function test_BatchUpdateScores_ArrayMismatchReverts() public {
        address[] memory tokens = new address[](2);
        tokens[0] = usdc;
        tokens[1] = usdt;

        uint16[] memory scores_ = new uint16[](1);
        scores_[0] = 8500;

        bytes2[] memory grades = new bytes2[](2);
        uint48[] memory timestamps = new uint48[](2);
        uint16[] memory versions = new uint16[](2);

        vm.prank(keeper);
        vm.expectRevert("Basis: array length mismatch");
        oracle.batchUpdateScores(tokens, scores_, grades, timestamps, versions);
    }

    function test_BatchUpdateScores_RejectsNonKeeper() public {
        address[] memory tokens = new address[](1);
        tokens[0] = usdc;
        uint16[] memory scores_ = new uint16[](1);
        scores_[0] = 8500;
        bytes2[] memory grades = new bytes2[](1);
        grades[0] = "A ";
        uint48[] memory timestamps = new uint48[](1);
        timestamps[0] = baseTimestamp;
        uint16[] memory versions = new uint16[](1);
        versions[0] = 1;

        vm.prank(nonKeeper);
        vm.expectRevert("Basis: not keeper");
        oracle.batchUpdateScores(tokens, scores_, grades, timestamps, versions);
    }

    // ═══════════════════════════════════════════════════════════
    // SII — getScore / isStale / getAllScores
    // ═══════════════════════════════════════════════════════════

    function test_GetScore_ReturnsZeroForUnscored() public {
        (uint16 score, bytes2 grade, uint48 ts, uint16 ver) = oracle.getScore(usdc);
        assertEq(score, 0);
        assertEq(grade, bytes2(0));
        assertEq(ts, 0);
        assertEq(ver, 0);
    }

    function test_IsStale_ReturnsTrueWhenNeverScored() public {
        assertTrue(oracle.isStale(usdc, 3600));
    }

    function test_IsStale_ReturnsFalseWhenFresh() public {
        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);
        assertFalse(oracle.isStale(usdc, 3600));
    }

    function test_IsStale_ReturnsTrueWhenStale() public {
        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);

        vm.warp(block.timestamp + 3601);
        assertTrue(oracle.isStale(usdc, 3600));
    }

    function test_GetScoredTokenCount_ReturnsCorrectCount() public {
        assertEq(oracle.getScoredTokenCount(), 0);

        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);
        assertEq(oracle.getScoredTokenCount(), 1);

        vm.prank(keeper);
        oracle.updateScore(usdt, 7200, "B ", baseTimestamp, 1);
        assertEq(oracle.getScoredTokenCount(), 2);
    }

    function test_GetAllScores_ReturnsAllScored() public {
        vm.startPrank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);
        oracle.updateScore(usdt, 7200, "B ", baseTimestamp, 1);
        vm.stopPrank();

        (address[] memory tokens, IBasisSIIOracle.Score[] memory allScores) = oracle.getAllScores();
        assertEq(tokens.length, 2);
        assertEq(allScores.length, 2);
        assertEq(tokens[0], usdc);
        assertEq(allScores[0].score, 8500);
        assertEq(tokens[1], usdt);
        assertEq(allScores[1].score, 7200);
    }

    function test_GetAllScores_EmptyWhenNoneScored() public {
        (address[] memory tokens, IBasisSIIOracle.Score[] memory allScores) = oracle.getAllScores();
        assertEq(tokens.length, 0);
        assertEq(allScores.length, 0);
    }

    // ═══════════════════════════════════════════════════════════
    // PSI — updatePsiScore
    // ═══════════════════════════════════════════════════════════

    function test_UpdatePsiScore_StoresCorrectly() public {
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);

        (uint16 score, bytes2 grade, uint48 ts, uint16 ver) = oracle.getPsiScore("aave");
        assertEq(score, 7400);
        assertEq(grade, "B+");
        assertEq(ts, baseTimestamp);
        assertEq(ver, 1);
    }

    function test_UpdatePsiScore_EmitsEvent() public {
        bytes32 expectedHash = keccak256(abi.encodePacked("aave"));
        vm.expectEmit(true, false, false, true);
        emit IBasisSIIOracle.PsiScoreUpdated(expectedHash, "aave", 7400, "B+", baseTimestamp, 1);
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);
    }

    function test_UpdatePsiScore_RejectsNonKeeper() public {
        vm.prank(nonKeeper);
        vm.expectRevert("Basis: not keeper");
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);
    }

    function test_UpdatePsiScore_RejectsEmptySlug() public {
        vm.prank(keeper);
        vm.expectRevert("Basis: empty slug");
        oracle.updatePsiScore("", 7400, "B+", baseTimestamp, 1);
    }

    function test_UpdatePsiScore_RejectsOverRange() public {
        vm.prank(keeper);
        vm.expectRevert("Basis: score out of range");
        oracle.updatePsiScore("aave", 10001, "A+", baseTimestamp, 1);
    }

    function test_UpdatePsiScore_RejectsFutureTimestamp() public {
        vm.prank(keeper);
        vm.expectRevert("Basis: future timestamp");
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp + 1000, 1);
    }

    function test_UpdatePsiScore_RejectsOldTimestamp() public {
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);

        vm.prank(keeper);
        vm.expectRevert("Basis: stale update");
        oracle.updatePsiScore("aave", 7500, "B+", baseTimestamp, 1);
    }

    function test_UpdatePsiScore_AcceptsNewerTimestamp() public {
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);

        vm.warp(block.timestamp + 100);
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7500, "B+", baseTimestamp + 100, 1);

        (uint16 score,,,) = oracle.getPsiScore("aave");
        assertEq(score, 7500);
    }

    function test_UpdatePsiScore_StoresSlugMapping() public {
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);

        bytes32 slugHash = keccak256(abi.encodePacked("aave"));
        assertEq(oracle.protocolSlugs(slugHash), "aave");
    }

    function test_UpdatePsiScore_TracksProtocolOnce() public {
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);
        assertEq(oracle.getPsiScoreCount(), 1);

        vm.warp(block.timestamp + 100);
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7500, "B+", baseTimestamp + 100, 1);
        assertEq(oracle.getPsiScoreCount(), 1);
    }

    // ═══════════════════════════════════════════════════════════
    // PSI — batchUpdatePsiScores
    // ═══════════════════════════════════════════════════════════

    function test_BatchUpdatePsiScores_Works() public {
        string[] memory slugs = new string[](2);
        slugs[0] = "aave";
        slugs[1] = "drift";

        uint16[] memory scores_ = new uint16[](2);
        scores_[0] = 7400;
        scores_[1] = 6800;

        bytes2[] memory grades = new bytes2[](2);
        grades[0] = "B+";
        grades[1] = "B ";

        uint48[] memory timestamps = new uint48[](2);
        timestamps[0] = baseTimestamp;
        timestamps[1] = baseTimestamp;

        uint16[] memory versions = new uint16[](2);
        versions[0] = 1;
        versions[1] = 1;

        vm.prank(keeper);
        oracle.batchUpdatePsiScores(slugs, scores_, grades, timestamps, versions);

        (uint16 s1,,,) = oracle.getPsiScore("aave");
        (uint16 s2,,,) = oracle.getPsiScore("drift");
        assertEq(s1, 7400);
        assertEq(s2, 6800);
        assertEq(oracle.getPsiScoreCount(), 2);
    }

    function test_BatchUpdatePsiScores_ArrayMismatchReverts() public {
        string[] memory slugs = new string[](2);
        slugs[0] = "aave";
        slugs[1] = "drift";

        uint16[] memory scores_ = new uint16[](1);
        scores_[0] = 7400;

        bytes2[] memory grades = new bytes2[](2);
        uint48[] memory timestamps = new uint48[](2);
        uint16[] memory versions = new uint16[](2);

        vm.prank(keeper);
        vm.expectRevert("Basis: array length mismatch");
        oracle.batchUpdatePsiScores(slugs, scores_, grades, timestamps, versions);
    }

    // ═══════════════════════════════════════════════════════════
    // PSI — getPsiScore / isPsiStale / getAllPsiScores
    // ═══════════════════════════════════════════════════════════

    function test_GetPsiScore_ReturnsZeroForUnscored() public {
        (uint16 score, bytes2 grade, uint48 ts, uint16 ver) = oracle.getPsiScore("unknown");
        assertEq(score, 0);
        assertEq(grade, bytes2(0));
        assertEq(ts, 0);
        assertEq(ver, 0);
    }

    function test_IsPsiStale_ReturnsTrueWhenNeverScored() public {
        assertTrue(oracle.isPsiStale("aave", 3600));
    }

    function test_IsPsiStale_ReturnsFalseWhenFresh() public {
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);
        assertFalse(oracle.isPsiStale("aave", 3600));
    }

    function test_IsPsiStale_ReturnsTrueWhenStale() public {
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);

        vm.warp(block.timestamp + 3601);
        assertTrue(oracle.isPsiStale("aave", 3600));
    }

    function test_GetPsiScoreCount_ReturnsCorrectCount() public {
        assertEq(oracle.getPsiScoreCount(), 0);

        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);
        assertEq(oracle.getPsiScoreCount(), 1);

        vm.prank(keeper);
        oracle.updatePsiScore("drift", 6800, "B ", baseTimestamp, 1);
        assertEq(oracle.getPsiScoreCount(), 2);
    }

    function test_GetAllPsiScores_ReturnsAllScored() public {
        vm.startPrank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);
        oracle.updatePsiScore("drift", 6800, "B ", baseTimestamp, 1);
        vm.stopPrank();

        (string[] memory slugs, IBasisSIIOracle.PsiScore[] memory allScores) = oracle.getAllPsiScores();
        assertEq(slugs.length, 2);
        assertEq(allScores.length, 2);
        assertEq(keccak256(bytes(slugs[0])), keccak256(bytes("aave")));
        assertEq(allScores[0].score, 7400);
        assertEq(keccak256(bytes(slugs[1])), keccak256(bytes("drift")));
        assertEq(allScores[1].score, 6800);
    }

    function test_GetAllPsiScores_EmptyWhenNoneScored() public {
        (string[] memory slugs, IBasisSIIOracle.PsiScore[] memory allScores) = oracle.getAllPsiScores();
        assertEq(slugs.length, 0);
        assertEq(allScores.length, 0);
    }

    // ═══════════════════════════════════════════════════════════
    // CQI — getCqi
    // ═══════════════════════════════════════════════════════════

    function test_GetCqi_ComputesCorrectly() public {
        // SII = 8800, PSI = 7400 → product = 65120000 → sqrt ≈ 8069
        vm.startPrank(keeper);
        oracle.updateScore(usdc, 8800, "A ", baseTimestamp, 1);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);
        vm.stopPrank();

        uint16 cqi = oracle.getCqi(usdc, "aave");
        // sqrt(65120000) = 8069.69... → 8069
        assertEq(cqi, 8069);
    }

    function test_GetCqi_ReturnsZeroIfSiiMissing() public {
        vm.prank(keeper);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);

        uint16 cqi = oracle.getCqi(usdc, "aave");
        assertEq(cqi, 0);
    }

    function test_GetCqi_ReturnsZeroIfPsiMissing() public {
        vm.prank(keeper);
        oracle.updateScore(usdc, 8800, "A ", baseTimestamp, 1);

        uint16 cqi = oracle.getCqi(usdc, "aave");
        assertEq(cqi, 0);
    }

    function test_GetCqi_ReturnsZeroIfBothMissing() public {
        uint16 cqi = oracle.getCqi(usdc, "aave");
        assertEq(cqi, 0);
    }

    function test_GetCqi_PerfectScores() public {
        // SII = 10000, PSI = 10000 → sqrt(100000000) = 10000
        vm.startPrank(keeper);
        oracle.updateScore(usdc, 10000, "A+", baseTimestamp, 1);
        oracle.updatePsiScore("aave", 10000, "A+", baseTimestamp, 1);
        vm.stopPrank();

        uint16 cqi = oracle.getCqi(usdc, "aave");
        assertEq(cqi, 10000);
    }

    function test_GetCqi_AsymmetricScores() public {
        // SII = 10000, PSI = 2500 → sqrt(25000000) = 5000
        vm.startPrank(keeper);
        oracle.updateScore(usdc, 10000, "A+", baseTimestamp, 1);
        oracle.updatePsiScore("aave", 2500, "C ", baseTimestamp, 1);
        vm.stopPrank();

        uint16 cqi = oracle.getCqi(usdc, "aave");
        assertEq(cqi, 5000);
    }

    function test_GetCqi_LowScores() public {
        // SII = 1000, PSI = 1000 → sqrt(1000000) = 1000
        vm.startPrank(keeper);
        oracle.updateScore(usdc, 1000, "D ", baseTimestamp, 1);
        oracle.updatePsiScore("aave", 1000, "D ", baseTimestamp, 1);
        vm.stopPrank();

        uint16 cqi = oracle.getCqi(usdc, "aave");
        assertEq(cqi, 1000);
    }

    // ═══════════════════════════════════════════════════════════
    // ADMIN — setKeeper / pause / unpause
    // ═══════════════════════════════════════════════════════════

    function test_SetKeeper_Works() public {
        address newKeeper = address(0xCAFE);
        oracle.setKeeper(newKeeper);
        assertEq(oracle.keeper(), newKeeper);
    }

    function test_SetKeeper_EmitsEvent() public {
        address newKeeper = address(0xCAFE);
        vm.expectEmit(true, true, false, false);
        emit IBasisSIIOracle.KeeperUpdated(keeper, newKeeper);
        oracle.setKeeper(newKeeper);
    }

    function test_SetKeeper_RejectsNonOwner() public {
        vm.prank(nonKeeper);
        vm.expectRevert("Basis: not owner");
        oracle.setKeeper(address(0xCAFE));
    }

    function test_SetKeeper_RejectsZeroAddress() public {
        vm.expectRevert("Basis: zero keeper");
        oracle.setKeeper(address(0));
    }

    function test_Pause_Works() public {
        oracle.pause();
        assertTrue(oracle.paused());
    }

    function test_Pause_EmitsEvent() public {
        vm.expectEmit(true, false, false, false);
        emit IBasisSIIOracle.Paused(owner);
        oracle.pause();
    }

    function test_Pause_BlocksUpdates() public {
        oracle.pause();

        vm.prank(keeper);
        vm.expectRevert("Basis: paused");
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);
    }

    function test_Pause_BlocksPsiUpdates() public {
        oracle.pause();

        vm.prank(keeper);
        vm.expectRevert("Basis: paused");
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);
    }

    function test_Unpause_Works() public {
        oracle.pause();
        oracle.unpause();
        assertFalse(oracle.paused());

        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);
        (uint16 score,,,) = oracle.getScore(usdc);
        assertEq(score, 8500);
    }

    function test_Unpause_EmitsEvent() public {
        oracle.pause();
        vm.expectEmit(true, false, false, false);
        emit IBasisSIIOracle.Unpaused(owner);
        oracle.unpause();
    }

    function test_Pause_RejectsNonOwner() public {
        vm.prank(nonKeeper);
        vm.expectRevert("Basis: not owner");
        oracle.pause();
    }

    function test_Unpause_RejectsNonOwner() public {
        oracle.pause();
        vm.prank(nonKeeper);
        vm.expectRevert("Basis: not owner");
        oracle.unpause();
    }

    // ═══════════════════════════════════════════════════════════
    // SAFE GUARD — Constructor
    // ═══════════════════════════════════════════════════════════

    function test_Guard_Constructor_SetsOracle() public {
        assertEq(address(guard.oracle()), address(oracle));
    }

    function test_Guard_Constructor_SetsThreshold() public {
        assertEq(guard.threshold(), 5000);
    }

    function test_Guard_Constructor_SetsCqiThresholdToSiiDefault() public {
        assertEq(guard.cqiThreshold(), 5000);
    }

    function test_Guard_Constructor_SetsMaxAge() public {
        assertEq(guard.maxScoreAge(), 3600);
    }

    function test_Guard_Constructor_RejectsZeroOracle() public {
        vm.expectRevert("Basis: zero oracle");
        new BasisSafeGuard(address(0), 5000, 3600);
    }

    // ═══════════════════════════════════════════════════════════
    // SAFE GUARD — Token management
    // ═══════════════════════════════════════════════════════════

    function test_Guard_AddToken() public {
        guard.addToken(usdc);
        assertTrue(guard.monitoredTokens(usdc));

        address[] memory tokens = guard.getMonitoredTokens();
        assertEq(tokens.length, 1);
        assertEq(tokens[0], usdc);
    }

    function test_Guard_RemoveToken() public {
        guard.addToken(usdc);
        guard.addToken(usdt);
        guard.removeToken(usdc);

        assertFalse(guard.monitoredTokens(usdc));
        address[] memory tokens = guard.getMonitoredTokens();
        assertEq(tokens.length, 1);
        assertEq(tokens[0], usdt);
    }

    function test_Guard_AddToken_RejectsDuplicate() public {
        guard.addToken(usdc);
        vm.expectRevert("Basis: already monitored");
        guard.addToken(usdc);
    }

    function test_Guard_RemoveToken_RejectsUnmonitored() public {
        vm.expectRevert("Basis: not monitored");
        guard.removeToken(usdc);
    }

    // ═══════════════════════════════════════════════════════════
    // SAFE GUARD — Protocol slugs
    // ═══════════════════════════════════════════════════════════

    function test_Guard_SetProtocolSlug() public {
        guard.setProtocolSlug(aavePool, "aave");
        assertEq(keccak256(bytes(guard.protocolSlugs(aavePool))), keccak256(bytes("aave")));
    }

    function test_Guard_SetProtocolSlug_RejectsNonOwner() public {
        vm.prank(nonKeeper);
        vm.expectRevert("Basis: not owner");
        guard.setProtocolSlug(aavePool, "aave");
    }

    // ═══════════════════════════════════════════════════════════
    // SAFE GUARD — CQI threshold
    // ═══════════════════════════════════════════════════════════

    function test_Guard_SetCqiThreshold() public {
        guard.setCqiThreshold(6000);
        assertEq(guard.cqiThreshold(), 6000);
    }

    function test_Guard_SetCqiThreshold_EmitsEvent() public {
        vm.expectEmit(false, false, false, true);
        emit BasisSafeGuard.CqiThresholdUpdated(5000, 6000);
        guard.setCqiThreshold(6000);
    }

    // ═══════════════════════════════════════════════════════════
    // SAFE GUARD — checkTransaction (SII)
    // ═══════════════════════════════════════════════════════════

    function test_Guard_AllowsHighSiiScore() public {
        guard.addToken(usdc);

        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);

        // Direct call to monitored token — should pass SII check
        guard.checkTransaction(
            usdc, 0, "", BasisSafeGuard.Operation.Call,
            0, 0, 0, address(0), payable(address(0)), "", address(0)
        );
    }

    function test_Guard_BlocksLowSiiScore() public {
        guard.addToken(usdc);

        vm.prank(keeper);
        oracle.updateScore(usdc, 3000, "D ", baseTimestamp, 1);

        vm.expectRevert("Basis: SII score below threshold");
        guard.checkTransaction(
            usdc, 0, "", BasisSafeGuard.Operation.Call,
            0, 0, 0, address(0), payable(address(0)), "", address(0)
        );
    }

    function test_Guard_BlocksStaleScore() public {
        guard.addToken(usdc);

        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);

        vm.warp(block.timestamp + 3601);
        vm.expectRevert("Basis: score is stale");
        guard.checkTransaction(
            usdc, 0, "", BasisSafeGuard.Operation.Call,
            0, 0, 0, address(0), payable(address(0)), "", address(0)
        );
    }

    function test_Guard_SkipsDelegateCall() public {
        guard.addToken(usdc);
        // DelegateCall bypasses guard — no revert
        guard.checkTransaction(
            usdc, 0, "", BasisSafeGuard.Operation.DelegateCall,
            0, 0, 0, address(0), payable(address(0)), "", address(0)
        );
    }

    function test_Guard_IgnoresUnmonitoredTokens() public {
        // No tokens monitored, no protocol set — should pass
        guard.checkTransaction(
            usdc, 0, "", BasisSafeGuard.Operation.Call,
            0, 0, 0, address(0), payable(address(0)), "", address(0)
        );
    }

    // ═══════════════════════════════════════════════════════════
    // SAFE GUARD — checkTransaction (CQI)
    // ═══════════════════════════════════════════════════════════

    function test_Guard_BlocksLowCqi() public {
        // Set up: USDC has high SII but aave has low PSI → low CQI
        guard.addToken(usdc);
        guard.setProtocolSlug(aavePool, "aave");
        guard.setCqiThreshold(7000);

        vm.startPrank(keeper);
        oracle.updateScore(usdc, 8000, "A ", baseTimestamp, 1);
        oracle.updatePsiScore("aave", 3000, "D ", baseTimestamp, 1);
        vm.stopPrank();

        // CQI = sqrt(8000 * 3000) = sqrt(24000000) ≈ 4898 < 7000
        // Call to aavePool with enough data to trigger protocol check
        bytes memory data = abi.encodeWithSignature("deposit(address,uint256)", usdc, 1000);

        vm.expectRevert("Basis: CQI score below threshold");
        guard.checkTransaction(
            aavePool, 0, data, BasisSafeGuard.Operation.Call,
            0, 0, 0, address(0), payable(address(0)), "", address(0)
        );
    }

    function test_Guard_AllowsHighCqi() public {
        guard.addToken(usdc);
        guard.setProtocolSlug(aavePool, "aave");
        guard.setCqiThreshold(7000);

        vm.startPrank(keeper);
        oracle.updateScore(usdc, 8800, "A ", baseTimestamp, 1);
        oracle.updatePsiScore("aave", 7400, "B+", baseTimestamp, 1);
        vm.stopPrank();

        // CQI = sqrt(8800 * 7400) = sqrt(65120000) ≈ 8069 > 7000
        bytes memory data = abi.encodeWithSignature("deposit(address,uint256)", usdc, 1000);

        guard.checkTransaction(
            aavePool, 0, data, BasisSafeGuard.Operation.Call,
            0, 0, 0, address(0), payable(address(0)), "", address(0)
        );
    }

    function test_Guard_FallsBackToSiiIfNoProtocol() public {
        guard.addToken(usdc);
        // aavePool is NOT registered as a protocol

        vm.prank(keeper);
        oracle.updateScore(usdc, 8500, "A ", baseTimestamp, 1);

        // Direct transfer to a non-protocol, non-token address with usdc in calldata
        // This should not trigger any check since `to` is not monitored or a protocol
        guard.checkTransaction(
            aavePool, 0, "", BasisSafeGuard.Operation.Call,
            0, 0, 0, address(0), payable(address(0)), "", address(0)
        );
    }

    // ═══════════════════════════════════════════════════════════
    // SAFE GUARD — Admin setters
    // ═══════════════════════════════════════════════════════════

    function test_Guard_SetThreshold() public {
        guard.setThreshold(7000);
        assertEq(guard.threshold(), 7000);
    }

    function test_Guard_SetMaxScoreAge() public {
        guard.setMaxScoreAge(7200);
        assertEq(guard.maxScoreAge(), 7200);
    }

    function test_Guard_SetOracle() public {
        BasisOracle newOracle = new BasisOracle(keeper);
        guard.setOracle(address(newOracle));
        assertEq(address(guard.oracle()), address(newOracle));
    }

    function test_Guard_SetOracle_RejectsZero() public {
        vm.expectRevert("Basis: zero oracle");
        guard.setOracle(address(0));
    }

    function test_Guard_SetThreshold_RejectsNonOwner() public {
        vm.prank(nonKeeper);
        vm.expectRevert("Basis: not owner");
        guard.setThreshold(7000);
    }

    // ═══════════════════════════════════════════════════════════
    // SAFE GUARD — checkAfterExecution
    // ═══════════════════════════════════════════════════════════

    function test_Guard_CheckAfterExecution_NoOp() public {
        guard.checkAfterExecution(bytes32(0), true);
    }
}
