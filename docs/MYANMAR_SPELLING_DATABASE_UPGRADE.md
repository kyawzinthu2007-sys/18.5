# Myanmar Spelling Database Upgrade

Updated: 2026-08-20

The Myanmar spelling checker has been expanded using internet-researched references rather than relying only on the original small hand-written list.

## References reviewed

1. Myanmar Computer Federation's Myanmar Spelling Book page, which identifies the Myanmar Language Commission's 2003 spelling book as a source.
2. kanaung/wordlists public Myanmar spelling-book word list (13,574 populated lines), intended for word segmentation/line breaking/spellchecking.
3. Myanmar Proverbs spelling reference, including common correct/incorrect pairs and references to Myanmar dictionaries/spelling books.
4. mySpellCorrect, an open-source Burmese spelling correction project using n-gram/SymSpell statistical methods.

## Behavior

- High-confidence wrong -> correct pairs are underlined in red.
- A suggested correction can be clicked and applied.
- Unknown/context-dependent words are not automatically marked wrong.
- The checker remains deterministic and does not require a local AI model.
- The database is stored in `backend/edu_app/myanmar_spelling.py` and source metadata is stored in `spelling_sources.json`.

## Important limitation

The online references include large word lists, but a word list alone cannot safely determine that every unknown Myanmar substring is misspelled because Myanmar text often has no spaces and many forms are context-dependent. Therefore this upgrade deliberately combines a researched spelling reference with conservative correction pairs instead of falsely flagging every word not present in a dictionary.
