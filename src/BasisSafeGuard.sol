// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IBasisSIIOracle} from "./interfaces/IBasisSIIOracle.sol";

/// @title BasisSafeGuard — Safe Guard module that checks SII and CQI before transactions
/// @notice Blocks Safe transactions involving low-score stablecoins or protocols.
///         When a target is a known protocol and involves a monitored token, CQI is checked.
///         Otherwise, falls back to SII-only check on the token.
contract BasisSafeGuard {
    // ─── Enums ───
    enum Operation { Call, DelegateCall }

    // ─── State ───
    address public owner;
    IBasisSIIOracle public oracle;
    uint16 public threshold;         // minimum SII score (0-10000)
    uint16 public cqiThreshold;      // minimum CQI score (0-10000)
    uint256 public maxScoreAge;      // max staleness in seconds

    // ─── Monitored tokens ───
    mapping(address => bool) public monitoredTokens;
    address[] public tokenList;

    // ─── Protocol registry ───
    mapping(address => string) public protocolSlugs;  // contract addr => "aave", "drift", etc.

    // ─── Events ───
    event ThresholdUpdated(uint16 oldThreshold, uint16 newThreshold);
    event CqiThresholdUpdated(uint16 oldThreshold, uint16 newThreshold);
    event MaxScoreAgeUpdated(uint256 oldAge, uint256 newAge);
    event TokenAdded(address indexed token);
    event TokenRemoved(address indexed token);
    event OracleUpdated(address indexed oldOracle, address indexed newOracle);
    event ProtocolSlugSet(address indexed contractAddr, string slug);

    // ─── Modifiers ───
    modifier onlyOwner() {
        require(msg.sender == owner, "Basis: not owner");
        _;
    }

    // ─── Constructor ───
    constructor(
        address _oracle,
        uint16 _threshold,
        uint256 _maxScoreAge
    ) {
        require(_oracle != address(0), "Basis: zero oracle");
        owner = msg.sender;
        oracle = IBasisSIIOracle(_oracle);
        threshold = _threshold;
        maxScoreAge = _maxScoreAge;
        cqiThreshold = _threshold; // default CQI threshold = SII threshold
    }

    // ─── Safe Guard Interface ───
    /// @notice Called by Safe before executing a transaction
    function checkTransaction(
        address to,
        uint256 value,
        bytes memory data,
        Operation operation,
        uint256 safeTxGas,
        uint256 baseGas,
        uint256 gasPrice,
        address gasToken,
        address payable refundReceiver,
        bytes memory,
        address
    ) external view {
        // Only check Call operations (not DelegateCall)
        if (operation != Operation.Call) return;

        // Check if `to` is a monitored token (direct transfer)
        if (monitoredTokens[to]) {
            _checkSiiScore(to);
            return;
        }

        // Check if `to` is a known protocol
        string memory slug = protocolSlugs[to];
        if (bytes(slug).length > 0 && data.length >= 36) {
            // For ERC-20 approve/transfer calls, the token is the `to` address
            // But here `to` is a protocol — check CQI for all monitored tokens
            // against this protocol. If any CQI is below threshold, revert.
            _checkCqiForProtocol(slug);
            return;
        }

        // If data contains a call to a monitored token (e.g. multicall),
        // extract the token from the first 20 bytes after the selector
        if (data.length >= 36) {
            address target = _extractAddress(data, 16);
            if (monitoredTokens[target]) {
                // Check if `to` is also a known protocol
                string memory targetSlug = protocolSlugs[to];
                if (bytes(targetSlug).length > 0) {
                    uint16 cqi = oracle.getCqi(target, targetSlug);
                    require(cqi == 0 || cqi >= cqiThreshold, "Basis: CQI score below threshold");
                } else {
                    _checkSiiScore(target);
                }
            }
        }
    }

    /// @notice Called by Safe after executing a transaction (no-op)
    function checkAfterExecution(bytes32, bool) external view {}

    // ─── Internal ───
    function _checkSiiScore(address token) internal view {
        require(!oracle.isStale(token, maxScoreAge), "Basis: score is stale");
        (uint16 score,,,) = oracle.getScore(token);
        require(score >= threshold, "Basis: SII score below threshold");
    }

    function _checkCqiForProtocol(string memory slug) internal view {
        uint256 len = tokenList.length;
        for (uint256 i = 0; i < len; i++) {
            address token = tokenList[i];
            uint16 cqi = oracle.getCqi(token, slug);
            // Only check if both scores exist (cqi > 0)
            if (cqi > 0) {
                require(cqi >= cqiThreshold, "Basis: CQI score below threshold");
            }
        }
    }

    function _extractAddress(bytes memory data, uint256 offset) internal pure returns (address) {
        address addr;
        // solhint-disable-next-line no-inline-assembly
        assembly {
            addr := mload(add(add(data, 32), offset))
        }
        return address(uint160(addr));
    }

    // ─── Admin ───
    function setThreshold(uint16 _threshold) external onlyOwner {
        uint16 old = threshold;
        threshold = _threshold;
        emit ThresholdUpdated(old, _threshold);
    }

    function setCqiThreshold(uint16 _cqiThreshold) external onlyOwner {
        uint16 old = cqiThreshold;
        cqiThreshold = _cqiThreshold;
        emit CqiThresholdUpdated(old, _cqiThreshold);
    }

    function setMaxScoreAge(uint256 _maxScoreAge) external onlyOwner {
        uint256 old = maxScoreAge;
        maxScoreAge = _maxScoreAge;
        emit MaxScoreAgeUpdated(old, _maxScoreAge);
    }

    function setOracle(address _oracle) external onlyOwner {
        require(_oracle != address(0), "Basis: zero oracle");
        address old = address(oracle);
        oracle = IBasisSIIOracle(_oracle);
        emit OracleUpdated(old, _oracle);
    }

    function addToken(address token) external onlyOwner {
        require(!monitoredTokens[token], "Basis: already monitored");
        monitoredTokens[token] = true;
        tokenList.push(token);
        emit TokenAdded(token);
    }

    function removeToken(address token) external onlyOwner {
        require(monitoredTokens[token], "Basis: not monitored");
        monitoredTokens[token] = false;
        // Remove from list (swap + pop)
        for (uint256 i = 0; i < tokenList.length; i++) {
            if (tokenList[i] == token) {
                tokenList[i] = tokenList[tokenList.length - 1];
                tokenList.pop();
                break;
            }
        }
        emit TokenRemoved(token);
    }

    function setProtocolSlug(address contractAddr, string calldata slug) external onlyOwner {
        protocolSlugs[contractAddr] = slug;
        emit ProtocolSlugSet(contractAddr, slug);
    }

    function getMonitoredTokens() external view returns (address[] memory) {
        return tokenList;
    }
}
