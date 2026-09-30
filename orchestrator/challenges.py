"""
Challenge registry — train, sealed held-out, live held-out, and controls.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from orchestrator import config

MANIFEST_PATH = Path(config.PROJECT_ROOT) / "challenges" / "manifest.json"
HELD_OUT_LIVE_DIR = Path(config.PROJECT_ROOT) / "challenges" / "held_out"

TIERS = ("train", "held_out_sealed", "held_out_live", "control", "benchmark")


@dataclass
class ChallengeTarget:
    name: str
    tier: str
    vuln_class: str
    source: str
    control: str | None = None
    contract_name: str | None = None

    @property
    def solidity_contract_name(self) -> str:
        return self.contract_name or self.name


def load_manifest() -> list[ChallengeTarget]:
    """Load all targets from manifest.json."""
    if not MANIFEST_PATH.exists():
        return _legacy_manifest()
    data = json.loads(MANIFEST_PATH.read_text())
    out = []
    for entry in data.get("targets", []):
        out.append(
            ChallengeTarget(
                name=entry["name"],
                tier=entry["tier"],
                vuln_class=entry.get("vuln_class", "general"),
                source=entry["source"],
                control=entry.get("control"),
                contract_name=entry.get("contract_name"),
            )
        )
    return out


def _legacy_manifest() -> list[ChallengeTarget]:
    """Fallback if manifest missing."""
    return [
        ChallengeTarget(
            "VulnerableVault", "train", "reentrancy", "contracts/VulnerableVault.sol", "SafeVault"
        ),
        ChallengeTarget(
            "SafeVault", "control", "reentrancy", "contracts/SafeVault.sol", None
        ),
        ChallengeTarget(
            "VulnerableTreasury",
            "held_out_sealed",
            "access_control",
            "challenges/sealed/VulnerableTreasurySealed.sol",
            "SafeTreasury",
        ),
        ChallengeTarget(
            "SafeTreasury", "control", "access_control", "contracts/SafeTreasury.sol", None
        ),
    ]


def get_target(name: str) -> ChallengeTarget | None:
    for t in load_manifest():
        if t.name == name:
            return t
    return None


def list_targets(tiers: list[str] | None = None) -> list[ChallengeTarget]:
    targets = load_manifest()
    if tiers:
        return [t for t in targets if t.tier in tiers]
    return targets


def list_deployable() -> list[ChallengeTarget]:
    """All manifest entries that should be deployed (including controls)."""
    return load_manifest()


def list_for_dashboard() -> list[ChallengeTarget]:
    """Vulnerable targets + controls for UI."""
    return load_manifest()


def list_pipeline_targets(tier_filter: str | None = None) -> list[str]:
    """Names to run in CLI pipeline."""
    if tier_filter:
        return [t.name for t in list_targets([tier_filter])]
    return [t.name for t in load_manifest()]


def list_held_out_vulnerable() -> list[ChallengeTarget]:
    return [
        t
        for t in load_manifest()
        if t.tier in ("held_out_sealed", "held_out_live")
    ]


def resolve_source_path(target: ChallengeTarget) -> Path:
    """Absolute path to Solidity source for compilation."""
    if target.tier == "held_out_live":
        live_path = HELD_OUT_LIVE_DIR / f"{target.name}.sol"
        if live_path.exists():
            return live_path
        raise FileNotFoundError(
            f"Live held-out contract missing: {live_path}\n"
            f"Add {target.name}.sol under challenges/held_out/ before demo."
        )
    rel = Path(target.source)
    path = Path(config.PROJECT_ROOT) / rel
    if not path.exists():
        raise FileNotFoundError(f"Challenge source not found: {path}")
    return path


def resolve_source(name: str) -> str:
    """Read Solidity source for a target name."""
    target = get_target(name)
    if target is None:
        legacy = Path(config.PROJECT_ROOT) / "contracts" / f"{name}.sol"
        if legacy.exists():
            return legacy.read_text()
        raise ValueError(f"Unknown target: {name}")
    return resolve_source_path(target).read_text()


def manifest_summary() -> dict:
    """Grouped summary for dashboard API."""
    groups: dict[str, list[dict]] = {
        "train": [],
        "held_out": [],
        "benchmark": [],
        "control": [],
    }
    for t in load_manifest():
        row = {
            "name": t.name,
            "tier": t.tier,
            "vuln_class": t.vuln_class,
            "control": t.control,
        }
        if t.tier == "train":
            groups["train"].append(row)
        elif t.tier in ("held_out_sealed", "held_out_live"):
            groups["held_out"].append(row)
        elif t.tier == "benchmark":
            groups["benchmark"].append(row)
        elif t.tier == "control":
            groups["control"].append(row)
    return groups
