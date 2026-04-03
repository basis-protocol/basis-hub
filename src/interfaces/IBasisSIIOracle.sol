// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IBasisSIIOracle {
    // ─── SII Types ───
    struct Score {
        uint16 score;       // 0-10000 (basis points)
        bytes2 grade;       // ASCII grade e.g. "A+", "B "
        uint48 timestamp;   // Score calculation time
        uint16 version;     // Formula version
    }

    // ─── PSI Types ───
    struct PsiScore {
        uint16 score;       // 0-10000
        bytes2 grade;       // ASCII grade
        uint48 timestamp;   // Score calculation time
        uint16 version;     // Formula version
    }

    // ─── SII Events ───
    event ScoreUpdated(
        address indexed token,
        uint16 score,
        bytes2 grade,
        uint48 timestamp,
        uint16 version
    );

    // ─── PSI Events ───
    event PsiScoreUpdated(
        bytes32 indexed slugHash,
        string slug,
        uint16 score,
        bytes2 grade,
        uint48 timestamp,
        uint16 version
    );

    // ─── Admin Events ───
    event KeeperUpdated(address indexed oldKeeper, address indexed newKeeper);
    event Paused(address indexed by);
    event Unpaused(address indexed by);

    // ─── SII Functions ───
    function updateScore(
        address token,
        uint16 score,
        bytes2 grade,
        uint48 timestamp,
        uint16 version
    ) external;

    function batchUpdateScores(
        address[] calldata tokens,
        uint16[] calldata scores_,
        bytes2[] calldata grades,
        uint48[] calldata timestamps,
        uint16[] calldata versions
    ) external;

    function getScore(address token) external view returns (
        uint16 score, bytes2 grade, uint48 timestamp, uint16 version
    );

    function isStale(address token, uint256 maxAge) external view returns (bool);

    function getScoredTokenCount() external view returns (uint256);

    function getAllScores() external view returns (
        address[] memory tokens, Score[] memory allScores
    );

    // ─── PSI Functions ───
    function updatePsiScore(
        string calldata protocolSlug,
        uint16 score,
        bytes2 grade,
        uint48 timestamp,
        uint16 version
    ) external;

    function batchUpdatePsiScores(
        string[] calldata slugs,
        uint16[] calldata scores_,
        bytes2[] calldata grades,
        uint48[] calldata timestamps,
        uint16[] calldata versions
    ) external;

    function getPsiScore(string calldata protocolSlug) external view returns (
        uint16 score, bytes2 grade, uint48 timestamp, uint16 version
    );

    function isPsiStale(string calldata protocolSlug, uint256 maxAge) external view returns (bool);

    function getPsiScoreCount() external view returns (uint256);

    function getAllPsiScores() external view returns (
        string[] memory slugs, PsiScore[] memory allScores
    );

    // ─── CQI Functions ───
    function getCqi(
        address siiToken,
        string calldata psiProtocolSlug
    ) external view returns (uint16 cqiScore);

    // ─── Admin Functions ───
    function setKeeper(address newKeeper) external;
    function pause() external;
    function unpause() external;
}
