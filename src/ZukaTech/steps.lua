return {
	WrapInFunction       = require("ZukaTech.steps.WrapInFunction");
	SplitStrings         = require("ZukaTech.steps.SplitStrings");
	Vmify                = require("ZukaTech.steps.Vmify");
	ConstantArray        = require("ZukaTech.steps.ConstantArray");
	ProxifyLocals        = require("ZukaTech.steps.ProxifyLocals");
	AntiTamper           = require("ZukaTech.steps.AntiTamper");
	EncryptStrings       = require("ZukaTech.steps.EncryptStrings");
	NumbersToExpressions = require("ZukaTech.steps.NumbersToExpressions");
	AddVararg            = require("ZukaTech.steps.AddVararg");
	WatermarkCheck       = require("ZukaTech.steps.WatermarkCheck");
	JunkStatements       = require("ZukaTech.steps.JunkStatements");
	FakeLoopWrap         = require("ZukaTech.steps.FakeLoopWrap");
	-- Tier 1 upgrades
	DynamicXOR           = require("ZukaTech.steps.DynamicXOR");
	OpaquePredicates     = require("ZukaTech.steps.OpaquePredicates");
	AntiDump             = require("ZukaTech.steps.AntiDump");
	IntegrityHash        = require("ZukaTech.steps.IntegrityHash");
	VirtualGlobals       = require("ZukaTech.steps.VirtualGlobals");
}
