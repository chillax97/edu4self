# SAF sample: license and attribution

`sample.jsonl` in this folder holds 100 answers taken from the **SAF English set**
(Short Answer Feedback, communication networks), by Anna Filighera, Siddharth Parihar, Tim Steuer,
Tobias Meuser and Sebastian Ochs:

> Filighera et al. 2022. "Your Answer is Incorrect... Would you like to know why? Introducing a Bilingual
> Short Answer Feedback Dataset." Proceedings of ACL 2022, pages 8577-8591.
> https://aclanthology.org/2022.acl-long.587

Source: https://huggingface.co/datasets/Short-Answer-Feedback/saf_communication_networks_english
(revision `9358d6f0f87371c0a5f150502b14cb16e382195f`), the authors' own Hugging Face organisation:
the first author is one of its members, and the authors' code repository
(https://github.com/SebOchs/SAF) points there for the current version of the dataset.

**License: Creative Commons Attribution 4.0 International (CC BY 4.0)**,
https://creativecommons.org/licenses/by/4.0/. The dataset card declares `license: cc-by-4.0`.
This sample stays under CC BY 4.0. It is not covered by the MIT license of the rest of this repository.

**Changes made:** 100 of the 854 answers in the two test splits were picked (see `fetch_saf.py` and
`ids.txt`); the fields were renamed (`provided_answer` -> `answer`, `reference_answer` -> `reference`); the
experts' written feedback (`answer_feedback`) was left out; the label (`verification_feedback`) was mapped
to `gold` (Correct -> pass, Partially correct -> partial, Incorrect -> fail); and `id`, `qid`, `title`,
`category`, `reason` and `saf_split` were added. The question, reference answer and student answer
texts are unchanged.
