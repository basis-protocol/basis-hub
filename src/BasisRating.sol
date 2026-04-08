// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";

/// @title BasisRating — Soulbound Risk Rating Tokens
/// @notice Non-transferable ERC-721 tokens representing SII/PSI risk ratings.
///         Each token links to a Proof page and a report attestation hash.
contract BasisRating is ERC721 {

    struct Rating {
        bytes32 entityId;
        uint8   entityType;    // 0 = stablecoin (SII), 1 = protocol (PSI)
        uint16  score;         // 0-10000
        bytes2  grade;
        uint8   confidence;    // 0 = limited, 1 = standard, 2 = high
        bytes32 reportHash;
        uint48  timestamp;
        uint16  methodVersion;
    }

    mapping(uint256 => Rating) public ratings;
    mapping(bytes32 => uint256) public entityToToken;
    uint256 private _nextTokenId;

    address public keeper;
    string public baseURI;

    error NotKeeper();

    modifier onlyKeeper() {
        if (msg.sender != keeper) revert NotKeeper();
        _;
    }

    constructor(string memory _baseURI) ERC721("Basis Rating", "BRATE") {
        keeper = msg.sender;
        baseURI = _baseURI;
    }

    function mintRating(
        address recipient,
        bytes32 entityId,
        uint8   entityType,
        uint16  score,
        bytes2  grade,
        uint8   confidence,
        bytes32 reportHash,
        uint16  methodVersion
    ) external onlyKeeper returns (uint256) {
        uint256 tokenId = _nextTokenId++;
        _mint(recipient, tokenId);

        ratings[tokenId] = Rating({
            entityId: entityId,
            entityType: entityType,
            score: score,
            grade: grade,
            confidence: confidence,
            reportHash: reportHash,
            timestamp: uint48(block.timestamp),
            methodVersion: methodVersion
        });

        entityToToken[entityId] = tokenId;
        return tokenId;
    }

    /// @notice Update an existing rating's score data
    function updateRating(
        uint256 tokenId,
        uint16  score,
        bytes2  grade,
        uint8   confidence,
        bytes32 reportHash,
        uint16  methodVersion
    ) external onlyKeeper {
        require(_ownerOf(tokenId) != address(0), "Token does not exist");
        Rating storage r = ratings[tokenId];
        r.score = score;
        r.grade = grade;
        r.confidence = confidence;
        r.reportHash = reportHash;
        r.timestamp = uint48(block.timestamp);
        r.methodVersion = methodVersion;
    }

    function setBaseURI(string memory _baseURI) external onlyKeeper {
        baseURI = _baseURI;
    }

    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        require(_ownerOf(tokenId) != address(0), "Token does not exist");
        return string(abi.encodePacked(baseURI, _toString(tokenId)));
    }

    /// @dev Soulbound: only allow minting (from = address(0)), block transfers
    function _update(address to, uint256 tokenId, address auth) internal override returns (address) {
        address from = _ownerOf(tokenId);
        require(from == address(0), "Soulbound: non-transferable");
        return super._update(to, tokenId, auth);
    }

    function _toString(uint256 value) internal pure returns (string memory) {
        if (value == 0) return "0";
        uint256 temp = value;
        uint256 digits;
        while (temp != 0) { digits++; temp /= 10; }
        bytes memory buffer = new bytes(digits);
        while (value != 0) {
            digits--;
            buffer[digits] = bytes1(uint8(48 + value % 10));
            value /= 10;
        }
        return string(buffer);
    }
}
