# Local research inputs

Put the filtered FNSPID CSV in this directory as `Stock_news.csv`. CSV and JSONL
data files in this directory are ignored by Git. Docker mounts the directory
read-only at `/app/research-inputs`.

Save the official FNSPID file as `Stock_news_full.csv`, then prepare a study-sized file:

```powershell
docker run --rm -v "C:\Users\paul9\Desktop\114-2\專題\stance-shift-lab\research-inputs:/inputs" stance-shift-lab-research python scripts/prepare_fnspid_news.py /inputs/Stock_news_full.csv /inputs/Stock_news.csv
```

Then set this value in `.env.research` and restart the service:

```text
FNSPID_NEWS_PATH=/app/research-inputs/Stock_news.csv
```

The application reads either the original FNSPID columns
(`Date`, `Article_title`, `Stock_symbol`, `Url`) or the local filtered aliases
(`date`, `headline`, `symbol`, `url`). The headline becomes the sentiment
evidence text. Only rows for the selected ticker within the 90 days before the
analysis date are used.
