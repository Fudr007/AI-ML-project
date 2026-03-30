import json

def filter_it():
    trash = 0
    good = 0
    total = 0

    with open("bundesliga_data_w_kurz.jsonl", "r", encoding="utf-8") as fin, \
        open("bundesliga_data_filtered.jsonl", "w", encoding="utf-8") as fout:

        for line in fin:
            total += 1

            match_data = json.loads(line.strip())

            goly_domaci = int(match_data.get("goly_domaci", 0))
            goly_hoste = int(match_data.get("goly_hoste", 0))

            kurz_domaci = match_data.get("kurz_domaci", None)
            kurz_hoste = match_data.get("kurz_hoste", None)
            kurz_remiza = match_data.get("kurz_remiza", None)

            if (goly_domaci == 0 and goly_hoste == 0) or (kurz_domaci is None and kurz_hoste is None and kurz_remiza is None):
                trash += 1
            else:
                fout.write(line)
                good += 1

    return good, trash, total

if __name__ == "__main__":
    a = filter_it()
    print("Good:"+str(a[0])+"\nTrash:"+str(a[1])+"\nTotal:"+str(a[2]))