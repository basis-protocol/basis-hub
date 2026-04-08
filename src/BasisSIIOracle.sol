// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IBasisSIIOracle} from "./interfaces/IBasisSIIOracle.sol";

/// @title BasisOracle — SII + PSI score oracle with on-chain CQI computation
/// @notice Stores Stablecoin Integrity Index (SII) scores keyed by token address
///         and Protocol Safety Index (PSI) scores keyed by protocol slug hash.
///         CQI = sqrt(SII * PSI) is computable as a view function.
contract BasisOracle is IBasisSIIOracle {
    // ─── Roles ───
    address public owner;
    address public keeper;

    // ─── Circuit breaker ───
    bool public paused;

    // ─── SII Storage ───
    mapping(address => Score) public scores;
    address[] public scoredTokens;
    mapping(address => bool) private _isScored;

    // ─── PSI Storage ───
    mapping(bytes32 => PsiScore) public psiScores;
    bytes32[] public scoredProtocols;
    mapping(bytes32 => bool) private _isPsiScored;
    mapping(bytes32 => string) public protocolSlugs; // hash => original slug

    // ─── Modifiers ───
    modifier onlyOwner() {
        require(msg.sender == owner, "Basis: not owner");
        _;
    }

    modifier onlyKeeper() {
        require(msg.sender == keeper, "Basis: not keeper");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Basis: paused");
        _;
    }

    // ─── Constructor ───
    constructor(address initialKeeper) {
        require(initialKeeper != address(0), "Basis: zero keeper");
        owner = msg.sender;
        keeper = initialKeeper;
    }

    // ═══════════════════════════════════════════════════════════
    // SII FUNCTIONS
    // ═══════════════════════════════════════════════════════════

    function updateScore(
        address token,
        uint16 score,
        bytes2 grade,
        uint48 timestamp,
        uint16 version
    ) public onlyKeeper whenNotPaused {
        require(token != address(0), "Basis: zero address");
        require(score <= 10000, "Basis: score out of range");
        require(timestamp <= uint48(block.timestamp), "Basis: future timestamp");
        require(timestamp > scores[token].timestamp, "Basis: stale update");

        scores[token] = Score(score, grade, timestamp, version);

        if (!_isScored[token]) {
            _isScored[token] = true;
            scoredTokens.push(token);
        }

        emit ScoreUpdated(token, score, grade, timestamp, version);
    }

    function batchUpdateScores(
        address[] calldata tokens,
        uint16[] calldata scores_,
        bytes2[] calldata grades,
        uint48[] calldata timestamps,
        uint16[] calldata versions
    ) external onlyKeeper whenNotPaused {
        require(
            tokens.length == scores_.length &&
            tokens.length == grades.length &&
            tokens.length == timestamps.length &&
            tokens.length == versions.length,
            "Basis: array length mismatch"
        );

        for (uint256 i = 0; i < tokens.length; i++) {
            updateScore(tokens[i], scores_[i], grades[i], timestamps[i], versions[i]);
        }
    }

    function getScore(address token) external view returns (
        uint16, bytes2, uint48, uint16
    ) {
        Score memory s = scores[token];
        return (s.score, s.grade, s.timestamp, s.version);
    }

    function isStale(address token, uint256 maxAge) external view returns (bool) {
        Score memory s = scores[token];
        if (s.timestamp == 0) return true;
        return (block.timestamp - s.timestamp) > maxAge;
    }

    function getScoredTokenCount() external view returns (uint256) {
        return scoredTokens.length;
    }

    function getAllScores() external view returns (
        address[] memory, Score[] memory
    ) {
        uint256 len = scoredTokens.length;
        Score[] memory allScores = new Score[](len);
        for (uint256 i = 0; i < len; i++) {
            allScores[i] = scores[scoredTokens[i]];
        }
        return (scoredTokens, allScores);
    }

    // ═══════════════════════════════════════════════════════════
    // PSI FUNCTIONS
    // ═══════════════════════════════════════════════════════════

    function updatePsiScore(
        string calldata protocolSlug,
        uint16 score,
        bytes2 grade,
        uint48 timestamp,
        uint16 version
    ) public onlyKeeper whenNotPaused {
        require(bytes(protocolSlug).length > 0, "Basis: empty slug");
        require(score <= 10000, "Basis: score out of range");
        require(timestamp <= uint48(block.timestamp), "Basis: future timestamp");

        bytes32 slugHash = keccak256(abi.encodePacked(protocolSlug));
        require(timestamp > psiScores[slugHash].timestamp, "Basis: stale update");

        psiScores[slugHash] = PsiScore(score, grade, timestamp, version);

        if (!_isPsiScored[slugHash]) {
            _isPsiScored[slugHash] = true;
            scoredProtocols.push(slugHash);
            protocolSlugs[slugHash] = protocolSlug;
        }

        emit PsiScoreUpdated(slugHash, protocolSlug, score, grade, timestamp, version);
    }

    function batchUpdatePsiScores(
        string[] calldata slugs,
        uint16[] calldata scores_,
        bytes2[] calldata grades,
        uint48[] calldata timestamps,
        uint16[] calldata versions
    ) external onlyKeeper whenNotPaused {
        require(
            slugs.length == scores_.length &&
            slugs.length == grades.length &&
            slugs.length == timestamps.length &&
            slugs.length == versions.length,
            "Basis: array length mismatch"
        );

        for (uint256 i = 0; i < slugs.length; i++) {
            updatePsiScore(slugs[i], scores_[i], grades[i], timestamps[i], versions[i]);
        }
    }

    function getPsiScore(string calldata protocolSlug) external view returns (
        uint16, bytes2, uint48, uint16
    ) {
        bytes32 slugHash = keccak256(abi.encodePacked(protocolSlug));
        PsiScore memory s = psiScores[slugHash];
        return (s.score, s.grade, s.timestamp, s.version);
    }

    function isPsiStale(string calldata protocolSlug, uint256 maxAge) external view returns (bool) {
        bytes32 slugHash = keccak256(abi.encodePacked(protocolSlug));
        PsiScore memory s = psiScores[slugHash];
        if (s.timestamp == 0) return true;
        return (block.timestamp - s.timestamp) > maxAge;
    }

    function getPsiScoreCount() external view returns (uint256) {
        return scoredProtocols.length;
    }

    function getAllPsiScores() external view returns (
        string[] memory, PsiScore[] memory
    ) {
        uint256 len = scoredProtocols.length;
        string[] memory slugs = new string[](len);
        PsiScore[] memory allScores = new PsiScore[](len);
        for (uint256 i = 0; i < len; i++) {
            bytes32 h = scoredProtocols[i];
            slugs[i] = protocolSlugs[h];
            allScores[i] = psiScores[h];
        }
        return (slugs, allScores);
    }

    // ═══════════════════════════════════════════════════════════
    // CQI — Composite Quality Index
    // ═══════════════════════════════════════════════════════════

    /// @notice CQI = sqrt(SII * PSI). Returns 0 if either score is missing.
    function getCqi(
        address siiToken,
        string calldata psiProtocolSlug
    ) external view returns (uint16 cqiScore) {
        Score memory sii = scores[siiToken];
        bytes32 slugHash = keccak256(abi.encodePacked(psiProtocolSlug));
        PsiScore memory psi = psiScores[slugHash];

        if (sii.score == 0 || psi.score == 0) return 0;

        // Both are 0-10000, product fits in uint32
        uint256 product = uint256(sii.score) * uint256(psi.score);
        cqiScore = uint16(_sqrt(product));
    }

    function _sqrt(uint256 x) internal pure returns (uint256) {
        if (x == 0) return 0;
        uint256 z = (x + 1) / 2;
        uint256 y = x;
        while (z < y) {
            y = z;
            z = (x / z + z) / 2;
        }
        return y;
    }

    // ═══════════════════════════════════════════════════════════
    // REPORT ATTESTATION
    // ═══════════════════════════════════════════════════════════

    mapping(bytes32 => bytes32) public reportHashes;
    mapping(bytes32 => uint48)  public reportTimestamps;
    mapping(bytes32 => bytes4)  public reportLenses;


    /// @notice Publish the content hash of an off-chain report.
    /// @param entityId Canonical entity identifier (keccak256 of symbol/slug)
    /// @param reportHash SHA-256 content hash of the report data
    /// @param lensId Regulatory lens used (e.g., "SCO6") or 0x0 for none
    function publishReportHash(
        bytes32 entityId,
        bytes32 reportHash,
        bytes4  lensId
    ) external onlyKeeper whenNotPaused {
        reportHashes[entityId] = reportHash;
        reportTimestamps[entityId] = uint48(block.timestamp);
        reportLenses[entityId] = lensId;
        emit ReportPublished(entityId, reportHash, lensId, uint48(block.timestamp));
    }

    function getReportHash(bytes32 entityId) external view returns (
        bytes32 reportHash,
        bytes4  lensId,
        uint48  timestamp
    ) {
        return (reportHashes[entityId], reportLenses[entityId], reportTimestamps[entityId]);
    }

    // ═══════════════════════════════════════════════════════════
    // STATE ROOT
    // ═══════════════════════════════════════════════════════════

    bytes32 public latestStateRoot;
    uint48  public stateRootTimestamp;


    /// @notice Publish the daily state root — covers all attestation domains.
    /// @param stateRoot Content hash of the pulse state_root object
    function publishStateRoot(bytes32 stateRoot) external onlyKeeper whenNotPaused {
        latestStateRoot = stateRoot;
        stateRootTimestamp = uint48(block.timestamp);
        emit StateRootPublished(stateRoot, uint48(block.timestamp));
    }

    // ═══════════════════════════════════════════════════════════
    // ADMIN
    // ═══════════════════════════════════════════════════════════

    function setKeeper(address newKeeper) external onlyOwner {
        require(newKeeper != address(0), "Basis: zero keeper");
        address old = keeper;
        keeper = newKeeper;
        emit KeeperUpdated(old, newKeeper);
    }

    function pause() external onlyOwner {
        paused = true;
        emit Paused(msg.sender);
    }

    function unpause() external onlyOwner {
        paused = false;
        emit Unpaused(msg.sender);
    }
}
