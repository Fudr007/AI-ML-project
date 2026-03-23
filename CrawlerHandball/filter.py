import json

def filter_it():
    trash = 0
    good = 0
    total = 0

    with open("bundesliga_data.jsonl", "r", encoding="utf-8") as fin, \
        open("bundesliga_data_filtered.jsonl", "w", encoding="utf-8") as fout:

        for line in fin:
            total += 1

            match_data = json.loads(line.strip())

            goly_domaci = int(match_data.get("goly_domaci", 0))
            goly_hoste = int(match_data.get("goly_hoste", 0))

            domaci_hraci = match_data.get("domaci_hraci", [])
            hoste_hraci = match_data.get("hoste_hraci", [])

            if (goly_domaci == 0 and goly_hoste == 0) or (len(domaci_hraci) == 0 and len(hoste_hraci) == 0):
                trash += 1
            else:
                fout.write(line)
                good += 1

    return good, trash, total

if __name__ == "__main__":
    a = filter_it()
    print("Good:"+str(a[0])+"\nTrash:"+str(a[1])+"\nTotal:"+str(a[2]))