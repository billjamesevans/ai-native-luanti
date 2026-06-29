// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later

#include "test.h"

#include "mock_server.h"
#include "settings.h"

class TestAIRuntime : public TestBase
{
public:
	TestAIRuntime() { TestManager::registerTestModule(this); }
	const char *getName() { return "TestAIRuntime"; }

	void runTests(IGameDef *gamedef);

	void testLuaContractsLoaded();
};

static TestAIRuntime g_test_instance;

void TestAIRuntime::runTests(IGameDef *gamedef)
{
	MockServer server(getTestTempDirectory());

	g_settings->setBool("ai_runtime.enable_smoke_command", true);
	g_settings->setBool("ai_runtime.enable_demo_benchmark_command", true);
	g_settings->setBool("ai_runtime.enable_model_adapter_probe_command", true);
	g_settings->setBool("ai_runtime.enable_agents_sdk_adapter", true);
	server.createScripting();
	try {
		std::string builtin = Server::getBuiltinLuaPath() + DIR_DELIM;
		auto script = server.getScriptIface();
		script->loadBuiltin();
		script->loadMod(builtin + "game" DIR_DELIM "tests" DIR_DELIM
				"test_ai_runtime.lua", BUILTIN_MOD_NAME);
	} catch (ModError &e) {
		g_settings->setBool("ai_runtime.enable_smoke_command", false);
		g_settings->setBool("ai_runtime.enable_demo_benchmark_command", false);
		g_settings->setBool("ai_runtime.enable_model_adapter_probe_command", false);
		g_settings->setBool("ai_runtime.enable_agents_sdk_adapter", false);
		rawstream << e.what() << std::endl;
		num_tests_failed = 1;
		return;
	}
	g_settings->setBool("ai_runtime.enable_smoke_command", false);
	g_settings->setBool("ai_runtime.enable_demo_benchmark_command", false);
	g_settings->setBool("ai_runtime.enable_model_adapter_probe_command", false);
	g_settings->setBool("ai_runtime.enable_agents_sdk_adapter", false);

	TEST(testLuaContractsLoaded);
}

void TestAIRuntime::testLuaContractsLoaded()
{
	UASSERT(true);
}
