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

    // ─── Report Attestation Events ───
    event ReportPublished(bytes32 indexed entityId, bytes32 reportHash, bytes4 lensId, uint48 timestamp);
    event StateRootPublished(bytes32 stateRoot, uint48 timestamp);

    // ─── Track Record Events (Bucket A1) ───
    event TrackRecordPublished(
        bytes32 indexed eventHash,
        bytes4  indexed eventType,
        bytes32 stateRootAtEvent,
        uint48  eventTimestamp,
        uint48  committedAt
    );

    // ─── Dispute Commitment Events (Bucket A4) ───
    event DisputeCommitmentPublished(
        bytes32 indexed disputeId,
        bytes4  indexed transitionKind,
        bytes32 commitmentHash,
        uint48  committedAt
    );

    // ─── Report Attestation Functions ───
    function publishReportHash(bytes32 entityId, bytes32 reportHash, bytes4 lensId) external;
    function getReportHash(bytes32 entityId) external view returns (bytes32 reportHash, bytes4 lensId, uint48 timestamp);
    function publishStateRoot(bytes32 stateRoot) external;
    function latestStateRoot() external view returns (bytes32);
    function stateRootTimestamp() external view returns (uint48);

    // ─── Track Record Functions ───
    function publishTrackRecord(
        bytes32 eventHash,
        bytes32 stateRootAtEvent,
        bytes4  eventType,
        uint48  eventTimestamp
    ) external;
    function getTrackRecord(bytes32 eventHash) external view returns (
        bytes32 stateRootAtEvent,
        bytes4  eventType,
        uint48  eventTimestamp,
        uint48  committedAt
    );
    function trackRecordCount() external view returns (uint256);

    // ─── Dispute Commitment Functions ───
    function publishDisputeHash(
        bytes32 disputeId,
        bytes4  transitionKind,
        bytes32 commitmentHash
    ) external;
    function getDisputeCommitment(
        bytes32 disputeId,
        bytes4  transitionKind
    ) external view returns (bytes32 commitmentHash, uint48 committedAt);

    // ─── Admin Functions ───
    function setKeeper(address newKeeper) external;
    function pause() external;
    function unpause() external;
}
