# INGESTION PIPELINE
## Input files
- currently only support pdf filetype

## Parsing 
- page with image content -> use llama parse
- page with chart content -> use llama parse 
- page with table content -> use pdf plumber
- scanned page -> use llama parse
- else (only text) -> use pypdf text extraction
- if llama parse is exeeded quota, then use paddle ocr but with notification

## Chunking
- chunk method: page (only)
- chunk size: default 1 
- chunk overlap: default 0

## Embedding
- chunks fields: filename (filterable, retrieveable), file_id (filterable, retrieveable), chunk_id, page (filterable, retrieveable), category (filterable, retrieveable), company (filterable, retrieveable), content (retrieveable), vector_content (embedded, vector searchable)

## Ingestion
- embedded chunks ingestion

## Mechanic compatibility
- delete document will delete the vector knowledge too
- uploading a file with already exist filename lead to upload error
- uploading bulk files with 2 or more files with  same filename lead to upload error


# DOCUMENT AGENT FLOW
## Input Validation Guardrails:
- Detection of PII data -> gracefull refusal, do not input any PII data
- Detection of prompt injection or jailbreak -> gracefull refusal, prompt contain unsafe instruction
- Detection NSFW statement (like crimes, pornography, human trafficing, LGBT, religion issue) -> gracefull refusal, prompt contains NSFW content
- Detection of unsafe character that potential break the prompt format (like using html tag to override the input into pure trusted content) -> cleaning the unsafe formating or terms (like html tag <trusted_content>...</trusted_content>, <safe_for_work>...</safe_for_work>, etc), after cleaned, then continue to main flow.
- Detect language that use by user or language that requested by user, that language will influence to what languange will be use to write the final answer

## Chat History
- Chat history aware, but prioritize last user message

## Intent classification:
- need_plan: 
> true if the user intent is complex request that can not be done only with single task. need to execute multiple task type like document_metadata, knowledge_retrieval, or summary according to proper ordering based on user context. It could be multiple of same task type or multiple of different task type, this mechanic is depend on user context.
> false if the user intent can be done with single task.
- social_question: true if the user just chit-chat like hello, thank you, bye, etc. -> answer directly, no need retrieval stage.

## Tasks:
- document_metadata: this task need evidence. looking for available knowledge base that binded with agent, like total document, and list document names.
- knowledge_retrieval: this task need evidence. looking for evidence or facts from available knowledge base.
- summary: this task no need evidence. user need to summarize the chat history, no retrieval needed.

## Retrieval Stage
- Available methods: BM25 key word search only, vector search only, and hybrid with RRF
- Default: hybrid with rrf
- Top K: 5

## After evidence retrieval stage:
- evidence_sufficient: evidence is relevant and sufficient to answer user's request. Continue to answer generation.
- evidence_not_sufficient: evidence is relevant but not sufficient to generate proper answer
- evidence_not_relevant: evidence is not relevant and not feasible to generate answer. Continue to rephrase the retireval query and execute the retrieval again. If the evidence still not relevant then return honest refusal answer and recommend to rephrase or ask another question, or user can give 

## Generation Stage
- use structured output with pydantic support (consistent output)
- max output token: 4096
- for model support thinking effort, set to medium
- for the answer that will be rendered in frontend should be streamed to avoid long awaiting by user
- for scenario that need evidence, citation is mandatory and should be given to user, use structured output for this. Do some research to implement proper and user friendly citation experience

## After answer generation stage, llm review and guradrails:
- correctness: true if the answer is proper and correct, else is false.
- grounded: true if the answer using internal knowledge, else is false. 
- clean_format: true if there is no broken format like markdown formating, and etc. else false then it need to be repaired until clean_format is true.
- contain_pii: true if there is any PII data, this should be masked until the containe_pii is false.

## Caching Mechanism
- (out of scope for current MVP)

## Logging
- this is mandatory and should be the first priority: check env setup, what env setup currently used, critical process error, critical information for debugging

## Observability
- LLM observability using langfuse free tier, one chat on trace id, use spans on the same trace id for sub process under the chat response process.
- Duration process using logged runtime in database too, so we can display it to the dashboard page.

## Eval before ships
- Construct proper evaluation dataset based on sample document `service-docintel\evals\sample_documents\Kirana_Logistics_Annual_Report_2025.pdf`, write the eval dataset in `service-docintel\evals\datasets\eval_dataset.jsonl` (need to be update, align to the current specification)

# FRONTEND
- Breakdown into login, knowledge management, agent, dashboard, admin page.
- Login page: use seed user username (admin) and password (123456). Do not complicated login, this is for demo project.
- Knowledge management page: user can upload (upload file, currently only support pdf file, size < 50mb>), process (running ingestion), delete documents (also delete the vector knowledge). User can see document list and status.
- Agent page: user can do chat with the document agent (input text only, output text and formated markdown or html support markdown). Agent response that contain citation must be rendered properly. During user send question and awaiting streaming response, frontend should be able to show interactive waiting buffer like in chat gpt or claude.
- Dashboard page: user can see summary of knowledge (total file and status) and agent activity (total questions, and time to final answer runtime) so user know the agent runtime fastest response, avg, or the most long runtime response.
- Admin page: user can modify chunk size, chunk overlap, the retrieval method, top k
- color pallette: #91BBBB, #429393, #9C9D6E, #FFFFFF


# TECHNOLOGY STACK
- LLM: gpt 6 luna 
- model embedding: text embedding 3 small 
- database: neon postgres free tier
- storage: Supabase s3
- vector database: qdrant cloud free tier
- LLM observability: Langfuse free tier
- Frontend: NextJS
- Deployment: Provide dockerfile for each service and frontend, I want to deploy in separate. I plan to deploy each on vercel.