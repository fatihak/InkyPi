# Plugin InkyPi « Transports IDFM »

Prochains bus, état et prochains trains d'une ligne RER, heure d'arrivée estimée —
données temps réel d'Île-de-France Mobilités (PRIM).

## Clé API

1. Compte gratuit sur https://prim.iledefrance-mobilites.fr
2. Abonne-toi à : *Prochains Passages – requête unitaire*, *Messages Info Trafic*,
   *Calculateur Île-de-France Mobilités – Accès générique (Navitia)*.
3. Dans le fichier `.env` à la racine d'InkyPi : `PRIM_API_KEY=ta_cle`
4. `sudo systemctl restart inkypi.service`

## Réglages

- **Arrêts** : un nom (« Joinville-le-Pont ») ou un identifiant
  (`STIF:StopArea:SP:12345:`). Un nom est résolu une fois puis mémorisé ; le nom
  trouvé pour l'arrêt de bus s'affiche en bas à gauche de l'écran — vérifie-le.
- **Mode démo** : données fictives, pratique pour régler la mise en page.

## Programmation

Crée une playlist « Matin » de 07:30 à 08:15 contenant ce plugin, avec un
rafraîchissement toutes les 2 à 3 min. Une playlist plus courte est prioritaire
sur ta playlist habituelle, et InkyPi ne redessine l'écran que si l'image a changé.
Laisse le compte à rebours et l'heure de MAJ désactivés pour profiter de ce
comportement (l'écran met ~30 s à se rafraîchir).

Limite : les playlists InkyPi n'ont pas de jours de semaine, le tracker
s'affichera aussi le week-end sur ce créneau.
