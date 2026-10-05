# Data and model notices

The code license in LICENSE does not license upstream data. The repository
contains download/processing scripts, aggregate measurements, fictional CI
fixtures and the public MedlinePlus question drafts. It redistributes no raw or
processed graph, embeddings, structural question corpus, graph-derived gold,
private review queue or per-question research result.

| Source | Terms and use in this project |
|---|---|
| [PrimeKG](https://github.com/mims-harvard/PrimeKG), [Harvard Dataverse](https://doi.org/10.7910/DVN/IXA7BM) | Software MIT is distinct from individual upstream dataset rights. Individual-source terms apply, including DrugBank non-commercial restrictions. Only selected structured relations and entity names are used; PrimeKG drug/disease descriptive text is excluded. No graph-derived content is redistributed. |
| [MONDO](https://github.com/monarch-initiative/mondo/blob/master/LICENSE) | CC BY 4.0. Disease labels, EXACT synonyms, MeSH xrefs and direct is_a orientation only. Local downloaded release: 2026-09-01. Attribute the Mondo/Monarch contributors; the source ontology is unchanged. |
| [HPO](https://human-phenotype-ontology.github.io/license.html) | HPO-specific attribution/integrity terms. This project uses the Human Phenotype Ontology, release 2026-09-01, for phenotype labels and EXACT/layperson synonyms. The ontology and its logical relations are not modified or redistributed. Acknowledge the Human Phenotype Ontology Consortium. |
| [MedlinePlus.gov](https://medlineplus.gov/about/using/usingcontent/) | NLM health-topic summaries are public-domain US government works. All English XML full-summary text is used with source URLs; linked third-party pages, A.D.A.M. content, drug monographs and images are not fetched. Public text question drafts retain MedlinePlus.gov attribution. XML snapshot dated 2026-10-03. |
| [openFDA](https://open.fda.gov/terms/) | FDA government material is public domain/CC0 unless noted; its terms identify possible private-party copyright exceptions. Manufacturer-supplied label text should not be assumed uniformly public domain. Local label retrieval/extraction only; no label text is committed. Attribution: Data provided by the US Food and Drug Administration (openFDA). No API key, at most 500 task requests. |
| [BioRED](https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/) | NCBI-hosted biomedical relation benchmark used locally for extraction diagnostics. Original abstract/source rights remain relevant; no corpus or per-document derived content is redistributed. BioRED native labels do not provide contraindication gold. |
| [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) | MIT model. Downloaded only through fastembed into the local ignored model cache; no weights or vectors are redistributed. |

PrimeKG citation: Chandak, Huang and Zitnik, *Building a knowledge graph to enable
precision medicine*, Scientific Data (2023),
[doi:10.1038/s41597-023-01960-3](https://doi.org/10.1038/s41597-023-01960-3).
Source hashes and generation metadata are in eval/datasets/MANIFEST.json and
local data/raw download manifests. Government hosting does not grant rights to
every linked third-party work. Review upstream terms before any redistribution
or commercial reuse. No upstream organization endorses this demonstration.

This project is a research and engineering demo. It is not clinically validated
and must not guide diagnosis, medication dosage or treatment decisions. Graph
association, model confidence, source agreement and automated evaluation do not
establish medical correctness or effectiveness.
