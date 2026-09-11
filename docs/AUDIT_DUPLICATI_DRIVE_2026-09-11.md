# Audit duplicati Google Drive, 11 settembre 2026

Questo manifesto registra esclusivamente duplicati verificati byte-per-byte.
Non autorizza cancellazioni automatiche. Un file entra in `DUPLICATO CERTO`
solo quando due oggetti Drive distinti hanno lo stesso SHA-256 e il confronto
dei byte coincide.

## Percorsi di riferimento

- Copia canonica: `GESTIONALE/12_EXCEL_DA_CLASSIFICARE/05_PERSONALE_PAGHE_CEDOLINI`
  - parent Drive ID: `1Z6MeMUoCv156JhQyfgYJ7CEVVQmTd4Mu`
- Copia di quarantena/storico: `_QUARANTENA_DUPLICATI/DUPLICATI/90_ARCHIVIO_STORICO/PROGETTI/excel`
  - parent Drive ID del livello `excel`: `1Xura3TVoMN0nhAKZTzB5nXyfmi4FhIVC`

Regola: la copia nel `GESTIONALE` canonico viene classificata `CONSERVA`; la
copia byte-identica già collocata nella quarantena duplicati viene classificata
`DUPLICATO CERTO - NON CANCELLATO` fino all'esecuzione esplicita della fase di
bonifica.

## Coppie verificate

| File | Drive ID da conservare | Drive ID duplicato in quarantena | SHA-256 | Esito |
| --- | --- | --- | --- | --- |
| `Registro_riordino_cedolini.xlsx` | `1thBp4LtoGIsFJXmH5gsmYEhpUryAkCWE` | `1J1aaOgR7eEeui8rUxxJRbbpbYXxqAjTI` | `25bfb400be5aced7891b75efb5dac92a553c06195b54b5448f80c1de12f1fdeb` | byte identici |
| `inserimento genedale.xlsx` | `1BipGSEgRLcECUwmrxyMfDqaGoe_Hw1-Z` | `1nvCFybuV3ftOFeY51N_bnqrfouSfEoX6` | `73d870b50abf4968e998acde96a356056b8c1cc069b597a44e929ea811c0a3bf` | byte identici |
| `Cedolini_Ceraldi.xlsx` | `1gR0ChzE6JalQgn3BsAs5SymV19uj6AHS` | `1HodcbED9B_6EKoDA5Uhj8zTjF7PIgvPI` | `29ad9563b50868f37f5b29197203d4d882e50304816812908b2ec9303f436db7` | byte identici |
| `Controllo_mesi_mancanti_per_dipendente.xlsx` | `1vcgy7U8AlGs6Fk4zy2giNOI_oJBIXkgl` | `1evFu7twEWJqF0vm9ue2c6asPU63A0B4Y` | `d267601ccf5949041ca274c87b5f273cfaa6eba2212a4bfe403a5a92089ad83b` | byte identici |
| `Paghe_Pagamenti_Ceraldi_2.xlsx` | `154If1vp2PVeu4A6HY4OLhpQMms7OHzUk` | `1hqPMIJNDGitETvp1Ji5hQrv43bTbD9AH` | `098916269c9fbc5f0db916da46131174c2b9eea02f3e0ec5859fdc06bf759ed4` | byte identici |
| `salari_2018-2023.xlsx` | `1KFLGPVx_8JVLQe7CVxBucYwQnYfIzltA` | `1OunMfLQDpmS-dZ7NmPquK96LEWmxSRkb` | `bde0b2a1f706f4fe37c3ca0516f169d2b656439c3db6bfc7e5d4bf5a8ae72997` | byte identici |

## Vincoli di bonifica

1. Non deduplicare mai per nome, dimensione, data o importo soltanto.
2. Stesso Drive file ID mostrato in più mappe storiche non è un duplicato fisico.
3. Per PDF amministrativi, oltre allo SHA-256 verificare anche identità del documento quando esistono metadati business rilevanti, ad esempio beneficiario/CRO-TRN, dipendente/periodo, F24/codici tributo, verbale/targa/numero.
4. Per immagini Lotti, verificare prima il riferimento persistente `foto_url` / `foto_files`; estensione o nome base non bastano.
5. Nessuna copia indicata in questo documento è stata cancellata durante l'audit.
