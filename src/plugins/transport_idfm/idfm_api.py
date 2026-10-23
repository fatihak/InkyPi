"""Accès aux API PRIM d'Île-de-France Mobilités (prochains passages, info trafic, itinéraire)."""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

import requests

logger = logging.getLogger(__name__)

BASE = "https://prim.iledefrance-mobilites.fr/marketplace"
TIMEOUT = 20


def norm(s: str) -> str:
    """Minuscules sans accents, pour comparer des noms d'arrêts ou de destinations."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def val(x):
    """Les champs SIRI Lite sont tantôt {"value": ...}, tantôt [{"value": ...}]."""
    if isinstance(x, list):
        x = x[0] if x else None
    if isinstance(x, dict):
        return x.get("value")
    return x


def liste(texte: str) -> list[str]:
    return [t.strip() for t in (texte or "").replace(";", ",").split(",") if t.strip()]


@dataclass
class Passage:
    ligne: str
    destination: str
    heure: datetime | None
    statut: str = ""

    @property
    def annule(self) -> bool:
        return norm(self.statut) == "cancelled"


@dataclass
class Etat:
    bus: list[Passage] = field(default_factory=list)
    rer: list[Passage] = field(default_factory=list)
    perturbations: list[str] = field(default_factory=list)
    trafic_connu: bool = False
    arrivee: datetime | None = None
    depart_trajet: datetime | None = None
    erreurs: list[str] = field(default_factory=list)


class PrimClient:
    def __init__(self, api_key: str, tz: tzinfo):
        self.api_key = api_key
        self.tz = tz

    # ------------------------------------------------------------------ HTTP
    def get(self, chemin: str, params: dict | None = None) -> dict:
        r = requests.get(f"{BASE}/{chemin}", params=params, timeout=TIMEOUT,
                         headers={"apikey": self.api_key, "Accept": "application/json"})
        if r.status_code in (401, 403):
            raise RuntimeError("clé API PRIM refusée")
        if r.status_code == 429:
            raise RuntimeError("quota PRIM atteint")
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------ arrêts
    def chercher_arret(self, texte: str) -> tuple[str, str]:
        """Renvoie (id Navitia, nom) du premier arrêt correspondant à `texte`."""
        data = self.get("v2/navitia/places", {"q": texte, "type[]": "stop_area", "count": 5})
        lieux = [p for p in data.get("places") or [] if p.get("embedded_type") in (None, "stop_area")]
        if not lieux:
            raise RuntimeError(f"arrêt introuvable : {texte}")
        return lieux[0]["id"], lieux[0].get("name", texte)

    @staticmethod
    def vers_siri(navitia_id: str) -> str:
        """stop_area:IDFM:71517 -> STIF:StopArea:SP:71517:"""
        if navitia_id.startswith("STIF:"):
            return navitia_id
        return f"STIF:StopArea:SP:{navitia_id.split(':')[-1]}:"

    @staticmethod
    def vers_navitia(ref: str) -> str:
        """STIF:StopArea:SP:71517: -> stop_area:IDFM:71517"""
        if ref.startswith("stop_area:"):
            return ref
        code = [p for p in ref.split(":") if p][-1]
        return f"stop_area:IDFM:{code}"

    # ------------------------------------------------------------------ passages
    def passages(self, monitoring_ref: str, line_ref: str | None = None) -> list[Passage]:
        params = {"MonitoringRef": monitoring_ref}
        if line_ref:
            params["LineRef"] = line_ref
        return self.extraire_passages(self.get("stop-monitoring", params))

    def heure(self, s: str | None) -> datetime | None:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(self.tz)
        except ValueError:
            return None

    def extraire_passages(self, data: dict) -> list[Passage]:
        res = []
        livraisons = data.get("Siri", {}).get("ServiceDelivery", {}).get("StopMonitoringDelivery", [])
        for liv in livraisons:
            for visite in liv.get("MonitoredStopVisit") or []:
                vj = visite.get("MonitoredVehicleJourney", {})
                call = vj.get("MonitoredCall", {})
                h = (call.get("ExpectedDepartureTime") or call.get("ExpectedArrivalTime")
                     or call.get("AimedDepartureTime") or call.get("AimedArrivalTime"))
                res.append(Passage(
                    ligne=str(val(vj.get("PublishedLineName")) or val(vj.get("LineRef")) or "?"),
                    destination=str(val(call.get("DestinationDisplay"))
                                    or val(vj.get("DestinationName")) or "?"),
                    heure=self.heure(h),
                    statut=str(call.get("DepartureStatus") or call.get("ArrivalStatus") or ""),
                ))
        limite = datetime.now(self.tz) - timedelta(minutes=1)
        res = [p for p in res if p.heure and p.heure >= limite]
        return sorted(res, key=lambda p: p.heure)

    # ------------------------------------------------------------------ info trafic
    def perturbations(self, line_ref: str) -> list[str]:
        return self.extraire_perturbations(self.get("general-message", {"LineRef": line_ref}))

    def extraire_perturbations(self, data: dict) -> list[str]:
        out = []
        maintenant = datetime.now(self.tz)
        livraisons = data.get("Siri", {}).get("ServiceDelivery", {}).get("GeneralMessageDelivery", [])
        for liv in livraisons:
            for msg in liv.get("InfoMessage") or []:
                fin = self.heure(msg.get("ValidUntilTime"))
                if fin and fin < maintenant:
                    continue
                if "perturbation" not in norm(str(val(msg.get("InfoChannelRef")) or "")):
                    continue
                for m in msg.get("Content", {}).get("Message") or []:
                    texte = " ".join(str(val(m.get("MessageText")) or "").split())
                    if texte:
                        out.append(texte)
                        break
        return list(dict.fromkeys(out))

    # ------------------------------------------------------------------ itinéraire
    def itineraire(self, depart: str, arrivee: str) -> tuple[datetime | None, datetime | None]:
        data = self.get("v2/navitia/journeys", {
            "from": depart, "to": arrivee,
            "datetime": datetime.now(self.tz).strftime("%Y%m%dT%H%M%S"),
            "data_freshness": "realtime", "count": 1,
        })
        trajets = data.get("journeys") or []
        if not trajets:
            return None, None

        def nav(s):
            return datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=self.tz) if s else None

        return nav(trajets[0].get("departure_date_time")), nav(trajets[0].get("arrival_date_time"))


def filtrer(passages: list[Passage], lignes: list[str], contient: str,
            exclure: list[str], nombre: int) -> list[Passage]:
    lignes_n = {norm(l) for l in lignes}
    contient_n = norm(contient)
    exclure_n = [norm(x) for x in exclure]
    out = [p for p in passages
           if (not lignes_n or norm(p.ligne) in lignes_n)
           and (not contient_n or contient_n in norm(p.destination))
           and not any(x in norm(p.destination) for x in exclure_n)]
    return out[:nombre]
