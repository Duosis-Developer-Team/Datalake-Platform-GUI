CREATE TABLE public.raw_brocade_san_fcport_1 (
	portname varchar(255) NULL,
	swfcporttype varchar(255) NULL,
	swfcportphystate varchar(255) NULL,
	swfcportopstatus varchar(255) NULL,
	swfcportadmstatus varchar(255) NULL,
	swfcportlinkstate varchar(255) NULL,
	swfcporttxtype varchar(255) NULL,
	swfcporttxframes int8 NULL,
	swfcportrxframes int8 NULL,
	swfcportrxc2frames int8 NULL,
	swfcportrxc3frames int8 NULL,
	swfcportrxlcs int8 NULL,
	swfcportrxmcasts int8 NULL,
	swfcporttoomanyrdys int8 NULL,
	swfcportnotxcredits int8 NULL,
	"timestamp" int8 NULL,
	time_difference int8 NULL
);