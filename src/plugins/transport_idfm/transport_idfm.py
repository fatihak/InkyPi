import logging
from datetime import datetime, timedelta

import pytz

from plugins.base_plugin.base_plugin import BasePlugin
from plugins.transport_idfm.idfm_api import Etat, Passage, PrimClient, filtrer, liste

logger = logging.getLogger(__name__)

ENV_KEY = "PRIM_API_KEY"
JOURS = ["Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim."]

DEFAUTS = {
    "title": "Départ travail",
    "busStop": "",
    "busLines": "106, 108, 110",
    "busDestination": "Joinville",
    "busCount": "4",
    "rerStop": "Joinville-le-Pont",
    "rerLineRef": "STIF:Line::C01742:",
    "rerLabel": "A",
    "rerExclude": "Boissy, Sucy, Varenne, Saint-Maur, Champigny",
    "rerCount": "3",
    "destinationStop": "Nanterre Préfecture",
}


def hhmm(d):
    return d.strftime("%Hh%M") if d else "--h--"


class TransportIdfm(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["api_key"] = {
            "required": True,
            "service": "Île-de-France Mobilités (PRIM)",
            "expected_key": ENV_KEY,
        }
        template_params["defaults"] = DEFAUTS
        return template_params

    # ------------------------------------------------------------------ helpers
    def _reglage(self, settings, cle):
        v = settings.get(cle)
        return v if v not in (None, "") else DEFAUTS.get(cle, "")

    def _resoudre(self, client, settings, cle):
        """Accepte un identifiant (STIF:… ou stop_area:…) ou un nom d'arrêt.
        Un nom est résolu une fois via Navitia puis mis en cache dans les réglages."""
        saisie = self._reglage(settings, cle).strip()
        if not saisie:
            raise RuntimeError(f"Réglage manquant : {cle}")
        if saisie.startswith(("STIF:", "stop_area:")):
            return client.vers_navitia(saisie), saisie
        cache = settings.get(f"_{cle}Cache") or {}
        if cache.get("saisie") != saisie:
            nid, nom = client.chercher_arret(saisie)
            cache = {"saisie": saisie, "id": nid, "nom": nom}
            settings[f"_{cle}Cache"] = cache
            logger.info(f"Arrêt '{saisie}' résolu en {nom} ({nid})")
        return cache["id"], cache["nom"]

    # ------------------------------------------------------------------ données
    def _collecter(self, client, s):
        e = Etat()
        noms = {}
        try:
            bus_id, noms["bus"] = self._resoudre(client, s, "busStop")
            ps = client.passages(client.vers_siri(bus_id))
            e.bus = filtrer(ps, liste(self._reglage(s, "busLines")),
                            self._reglage(s, "busDestination"), [],
                            int(self._reglage(s, "busCount")))
        except Exception as ex:  # noqa: BLE001 - affiché à l'écran
            logger.exception("Bus")
            e.erreurs.append(f"Bus : {ex}")
        try:
            rer_id, noms["rer"] = self._resoudre(client, s, "rerStop")
            ps = client.passages(client.vers_siri(rer_id), self._reglage(s, "rerLineRef"))
            e.rer = filtrer(ps, [], "", liste(self._reglage(s, "rerExclude")),
                            int(self._reglage(s, "rerCount")))
        except Exception as ex:  # noqa: BLE001
            logger.exception("RER")
            e.erreurs.append(f"RER : {ex}")
        try:
            e.perturbations = client.perturbations(self._reglage(s, "rerLineRef"))
            e.trafic_connu = True
        except Exception as ex:  # noqa: BLE001
            logger.exception("Info trafic")
            e.trafic_connu = False
            e.erreurs.append(f"Info trafic : {ex}")
        try:
            dest_id, noms["dest"] = self._resoudre(client, s, "destinationStop")
            if "bus" in noms:
                e.depart_trajet, e.arrivee = client.itineraire(bus_id, dest_id)
        except Exception as ex:  # noqa: BLE001
            logger.exception("Itinéraire")
            e.erreurs.append(f"Itinéraire : {ex}")
        return e, noms

    def _demo(self, maintenant):
        n = maintenant.replace(second=0, microsecond=0)
        m = lambda x: n + timedelta(minutes=x)  # noqa: E731
        e = Etat(
            bus=[Passage("108", "Joinville-le-Pont RER", m(3)),
                 Passage("106", "Joinville-le-Pont RER", m(7)),
                 Passage("110", "Joinville-le-Pont RER", m(9), statut="cancelled"),
                 Passage("108", "Joinville-le-Pont RER", m(15))],
            rer=[Passage("A", "Saint-Germain-en-Laye", m(14)),
                 Passage("A", "Cergy-le-Haut", m(19)),
                 Passage("A", "Poissy", m(24))],
            perturbations=["Trafic perturbé entre Vincennes et Nation en raison d'un incident "
                           "technique. Retards de 10 à 15 min à prévoir."],
            depart_trajet=m(3), arrivee=m(52),
        )
        e.trafic_connu = True
        return e, {"bus": "Mon arrêt (démo)", "rer": "Joinville-le-Pont", "dest": "Nanterre-Préfecture"}

    # ------------------------------------------------------------------ rendu
    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        tz = pytz.timezone(device_config.get_config("timezone", default="Europe/Paris"))
        maintenant = datetime.now(tz)

        if settings.get("demoMode") == "true":
            etat, noms = self._demo(maintenant)
        else:
            api_key = device_config.load_env_key(ENV_KEY)
            if not api_key:
                raise RuntimeError(f"Clé API manquante : ajoute {ENV_KEY}=... dans le fichier .env d'InkyPi.")
            etat, noms = self._collecter(PrimClient(api_key, tz), settings)
            if not (etat.bus or etat.rer or etat.arrivee) and etat.erreurs:
                # Rien d'exploitable : on remonte l'erreur à l'interface web
                raise RuntimeError(" | ".join(etat.erreurs))

        compte_a_rebours = settings.get("showCountdown") == "true"

        def bus_vue(p):
            mins = int((p.heure - maintenant).total_seconds() // 60) if p.heure else None
            return {
                "ligne": p.ligne, "heure": hhmm(p.heure), "annule": p.annule,
                "dans": (("à l'approche" if mins <= 0 else f"{mins} min")
                         if compte_a_rebours and mins is not None else ""),
            }

        duree = None
        if etat.depart_trajet and etat.arrivee:
            duree = int((etat.arrivee - etat.depart_trajet).total_seconds() // 60)

        params = {
            "title": self._reglage(settings, "title"),
            "date": f"{JOURS[maintenant.weekday()]} {maintenant:%d/%m}",
            "maj": hhmm(maintenant) if settings.get("showRefreshTime") == "true" else "",
            "bus": [bus_vue(p) for p in etat.bus],
            "bus_destination": self._reglage(settings, "busDestination"),
            "rer_label": self._reglage(settings, "rerLabel"),
            "rer_titre": f"→ {noms.get('dest', '')}" if noms.get("dest") else noms.get("rer", ""),
            "rer": [{"heure": hhmm(p.heure), "destination": p.destination, "annule": p.annule}
                    for p in etat.rer],
            "perturbation": etat.perturbations[0] if etat.perturbations else "",
            "trafic_connu": getattr(etat, "trafic_connu", False),
            "arrivee": hhmm(etat.arrivee) if etat.arrivee else "",
            "depart": hhmm(etat.depart_trajet) if etat.depart_trajet else "",
            "duree": duree,
            "dest_nom": noms.get("dest", self._reglage(settings, "destinationStop")),
            "arret_bus": noms.get("bus", ""),
            "erreurs": etat.erreurs,
            "plugin_settings": settings,
        }
        image = self.render_image(dimensions, "transport_idfm.html", "transport_idfm.css", params)
        if image is None:
            raise RuntimeError("Le rendu de l'image a échoué.")
        return image
