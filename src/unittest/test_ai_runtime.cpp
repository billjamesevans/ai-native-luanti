// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later

#include "test.h"

#include "mock_server.h"

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

	server.createScripting();
	try {
		std::string builtin = Server::getBuiltinLuaPath() + DIR_DELIM;
		auto script = server.getScriptIface();
		script->loadBuiltin();
		script->loadMod(builtin + "game" DIR_DELIM "tests" DIR_DELIM
				"test_ai_runtime.lua", BUILTIN_MOD_NAME);
	} catch (ModError &e) {
		rawstream << e.what() << std::endl;
		num_tests_failed = 1;
		return;
	}

	TEST(testLuaContractsLoaded);
}

void TestAIRuntime::testLuaContractsLoaded()
{
	UASSERT(true);
}
