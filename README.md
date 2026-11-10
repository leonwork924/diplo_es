# diplo_es — alertes BOE pour AGS Espagne

Surveille le Boletín Oficial del Estado (sections II.A « nombramientos / ceses » et II.B « concursos / convocatorias »,
**tous les ministères**) et prépare UNE alerte récapitulative en anglais : nominations et fins de mission d'ambassadeurs
(y compris représentants permanents), résolutions attribuant des postes à l'étranger (consuls généraux, conseillers,
offices économiques et commerciaux, conseillers du travail, de l'éducation...), et **vacantes** (postes à pourvoir, sans nom).

**Rien n'est envoyé automatiquement** (décision IT, comme diplo_fr) : le workflow remplit `data/outbox.json`,
`tools/create_outlook_drafts.ps1` crée le brouillon Outlook, tu relis et tu envoies toi-même.

## Premier démarrage (repo vide)
1. Clone le repo vide dans `C:\Users\deryckel-l\Documents\diplo_es`.
2. Dézippe le contenu du zip DANS ce dossier (le dossier `diplo_es` doit contenir `src`, `tools`, `README.md`...).
3. Dans PowerShell, depuis le dossier : `git add -A`, `git commit -m "Premier envoi diplo_es"`, `git push`.
4. GitHub > Settings > Actions > General > Workflow permissions : **Read and write permissions**. Repo en **privé**.
5. Ensuite, pour chaque nouveau zip : `powershell -ExecutionPolicy Bypass -File "...\diplo_es\deploy.ps1" -Zip "...\nouveau.zip" -Message "..."`

## Utilisation (GitHub > Actions > « diplo_es - alerte BOE » > Run workflow)
- **Test de l'accès au BOE** : dry_run coché, days_back `8`, save_samples coché si tu veux garder des réponses brutes
  (`data/samples/`) : le log affiche l'alerte complète sans rien écrire.
- **Historique 12 mois** (journal + Excel, aucune alerte) : backfill coché, days_back `365`. Donne le volume réel.
- **Run normal** : days_back `8`, tout décoché. Les textes déjà vus (`data/seen.json`) ne reviennent pas.
- **Destinataires** : `config.json` (par défaut seulement Leon). Ajoute Antonio / Sonia après validation du contenu.
- Résultats : `data/suivi_diplo_es.xlsx` (onglets Movements et Per month), `data/movements.json`, `data/outbox.json`.

## Brouillons Outlook (sur ton PC)
`powershell -ExecutionPolicy Bypass -File "...\diplo_es\tools\create_outlook_drafts.ps1"` (options : `-Depuis N`, `-Redo`,
`-Refaire "texte"`, `-MarquerTraite`, `-Page`, `-Yes`, comme pour diplo_fr).

## Limites connues
- Écrit d'après la documentation officielle de l'API et de vrais titres du BOE ; le premier dry-run est le vrai test.
- Les ambassadeurs sont lus dans le titre (nom + pays). Pour les résolutions et convocations, les lignes de l'annexe sont
  extraites automatiquement (simple) : le lien BOE fait foi. Un texte qui ressemble à un mouvement mais n'est pas reconnu
  tombe dans « To check ».
- Attachés de défense : non vus au BOE à titre individuel (à confirmer avec AGS Espagne). Autres ministères : à valider
  avec Antonio sur l'historique de 12 mois.
- Pas de lettre type ni d'e-mail suggéré pour le diplomate tant qu'AGS Espagne n'a pas fourni son modèle.
