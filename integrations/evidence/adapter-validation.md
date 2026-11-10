# Adapters and the pytest plugin against the real libraries (2026-11-10)

Run in a spare environment outside the repository (`uv pip install -e cli langchain-core openai llama-index-core pytest`),
with `python -m pytest cli/tests/test_adapters_real.py cli/tests/test_integrations.py`. The three tests of
`test_adapters_real.py` are skipped in a normal run, where the optional libraries are not installed.

| Library | Version used | What was checked |
|---|---|---|
| langchain-core | 1.7.7 | a real prompt-and-model chain (a fake chat model, no network) and a real `RunnableLambda` returning an answer and context |
| llama-index-core | 0.14.25 | a real vector index and query engine with a mock model and mock embeddings; the answer and the retrieved node text come back |
| openai | 3.49.0 | the real SDK sending requests over HTTP to a small local server: a plain answer and a tool call are both read correctly |
| pytest | 9.2.0 here, 9.1.1 in the project environment | the plugin loaded through its entry point in a real pytest run, with its summary and JSON report |

What this does **not** show: any hosted service (no OpenAI, Anthropic or LangSmith call was made), other versions of these
libraries, or real applications built on them. The OpenAI check uses the real client against a stand-in server.

Result of the run:

```text
tests/test_adapters_real.py::test_a_real_langchain_chain_is_checked_through_the_adapter PASSED
tests/test_adapters_real.py::test_a_real_llamaindex_query_engine_returns_its_answer_and_the_retrieved_text PASSED
tests/test_adapters_real.py::test_the_real_openai_sdk_is_used_for_answers_and_tool_calls PASSED
tests/test_integrations.py::test_a_case_passes_when_every_check_holds_and_is_recorded PASSED
tests/test_integrations.py::test_a_failing_case_names_every_problem_in_plain_words PASSED
tests/test_integrations.py::test_the_expected_answer_ignores_case_and_spacing PASSED
tests/test_integrations.py::test_results_from_any_library_become_one_reply[plain text-plain text-chunks0-tools0] PASSED
tests/test_integrations.py::test_results_from_any_library_become_one_reply[raw1-a-chunks1-tools1] PASSED
tests/test_integrations.py::test_results_from_any_library_become_one_reply[raw2-o-chunks2-tools2] PASSED
tests/test_integrations.py::test_results_from_any_library_become_one_reply[raw3-t-chunks3-tools3] PASSED
tests/test_integrations.py::test_results_from_any_library_become_one_reply[raw4-from a chat message-chunks4-tools4] PASSED
tests/test_integrations.py::test_results_from_any_library_become_one_reply[raw5-already-chunks5-tools5] PASSED
tests/test_integrations.py::test_serve_answers_verano_app_calls_with_the_function_and_reports_its_failures PASSED
tests/test_integrations.py::test_the_plugin_prints_a_summary_and_writes_a_json_report PASSED
tests/test_integrations.py::test_the_langchain_adapter_sends_the_input_as_given_or_under_a_key PASSED
tests/test_integrations.py::test_the_llamaindex_adapter_returns_the_response_and_the_retrieved_nodes PASSED
tests/test_integrations.py::test_the_openai_adapter_sends_the_system_prompt_and_reports_tool_calls PASSED
tests/test_integrations.py::test_a_missing_library_says_which_extra_to_install PASSED
tests/test_integrations.py::test_the_server_agrees_a_protocol_version_and_says_who_it_is PASSED
tests/test_integrations.py::test_every_tool_is_listed_with_schemas_and_the_writing_ones_are_marked PASSED
tests/test_integrations.py::test_a_writing_tool_is_refused_without_the_flag_and_the_refusal_names_it[create_project] PASSED
tests/test_integrations.py::test_a_writing_tool_is_refused_without_the_flag_and_the_refusal_names_it[run_evaluation] PASSED
tests/test_integrations.py::test_a_writing_tool_is_refused_without_the_flag_and_the_refusal_names_it[propose_improvement] PASSED
tests/test_integrations.py::test_a_writing_tool_is_refused_without_the_flag_and_the_refusal_names_it[accept_improvement] PASSED
tests/test_integrations.py::test_a_writing_tool_is_refused_without_the_flag_and_the_refusal_names_it[move_label] PASSED
tests/test_integrations.py::test_bad_calls_are_answered_in_words_and_never_crash_the_server PASSED
tests/test_integrations.py::test_the_server_reads_lines_answers_lines_and_survives_garbage PASSED
tests/test_integrations.py::test_a_read_tool_reads_and_a_write_tool_writes_only_with_the_flag PASSED
tests/test_integrations.py::test_importing_test_by_name_does_not_make_pytest_run_it PASSED
============================== 29 passed in 2.50s ==============================
```
