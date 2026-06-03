const std = @import("std");

pub const Protocol = enum(u32) {
    J1850VPW = 1,
    J1850PWM = 2,
    ISO9141 = 3,
    ISO14230 = 4,
    CAN = 5,
    ISO15765 = 6,
    SCI_A_ENGINE = 7,
    SCI_A_TRANS = 8,
    SCI_B_ENGINE = 9,
    SCI_B_TRANS = 10,
    _,
};

pub const FilterType = enum(u32) {
    PASS_FILTER = 1,
    BLOCK_FILTER = 2,
    FLOW_CONTROL = 3,
    _,
};

pub const ConnectFlag = packed struct(u32) {
    CAN_29BIT_ID: bool = false,
    ISO9141_NO_CHECKSUM: bool = false,
    ISO9141_K_LINE_ONLY: bool = false,
    _padding: u29 = 0,

    pub const NONE = 0;
    pub const CAN_29BIT_ID_MASK = 0x0100;
    pub const ISO9141_NO_CHECKSUM_MASK = 0x0200;
    pub const ISO9141_K_LINE_ONLY_MASK = 0x1000;
};

pub const IoctlID = enum(u32) {
    GET_CONFIG = 0x01,
    SET_CONFIG = 0x02,
    READ_VBATT = 0x03,
    FIVE_BAUD_INIT = 0x04,
    FAST_INIT = 0x05,
    CLEAR_TX_BUFFER = 0x07,
    CLEAR_RX_BUFFER = 0x08,
    CLEAR_PERIODIC_MSGS = 0x09,
    CLEAR_MSG_FILTERS = 0x0A,
    CLEAR_FUNCT_MSG_LOOKUP_TABLE = 0x0B,
    ADD_TO_FUNCT_MSG_LOOKUP_TABLE = 0x0C,
    DELETE_FROM_FUNCT_MSG_LOOKUP_TABLE = 0x0D,
    READ_PROG_VOLTAGE = 0x0E,
    _,
};

pub const ConfigParam = enum(u32) {
    DATA_RATE = 0x01,
    LOOPBACK = 0x03,
    NODE_ADDRESS = 0x04,
    NETWORK_LINE = 0x05,
    P1_MIN = 0x06,
    P1_MAX = 0x07,
    P2_MIN = 0x08,
    P2_MAX = 0x09,
    P3_MIN = 0x0A,
    P3_MAX = 0x0B,
    P4_MIN = 0x0C,
    P4_MAX = 0x0D,
    W0 = 0x19,
    W1 = 0x0E,
    W2 = 0x0F,
    W3 = 0x10,
    W4 = 0x11,
    W5 = 0x12,
    TIDLE = 0x13,
    TINIL = 0x14,
    TWUP = 0x15,
    PARITY = 0x16,
    BIT_SAMPLE_POINT = 0x17,
    SYNC_JUMP_WIDTH = 0x18,
    T1_MAX = 0x1A,
    T2_MAX = 0x1B,
    T3_MAX = 0x1C,
    T4_MAX = 0x1D,
    T5_MAX = 0x1E,
    ISO15765_BS = 0x1F,
    ISO15765_STMIN = 0x20,
    DATA_BITS = 0x21,
    FIVE_BAUD_MOD = 0x22,
    BS_TX = 0x23,
    STMIN_TX = 0x24,
    ISO15765_WFT_MAX = 0x25,
    CAN_MIXED_FORMAT = 0x8000,
    J1962_PINS = 0x8001,
    SW_CAN_HS_DATA_RATE = 0x8010,
    SW_CAN_SPEEDCHANGE_ENABLE = 0x8011,
    SW_CAN_RES_SWITCH = 0x8012,
    ACTIVE_CHANNELS = 0x8020,
    SAMPLE_RATE = 0x8021,
    SAMPLES_PER_READING = 0x8022,
    READINGS_PER_MSG = 0x8023,
    AVERAGING_METHOD = 0x8024,
    SAMPLE_RESOLUTION = 0x8025,
    INPUT_RANGE_LOW = 0x8026,
    INPUT_RANGE_HIGH = 0x8027,
    _,
};

pub const J2534Error = enum(u32) {
    STATUS_NOERROR = 0x00,
    ERR_NOT_SUPPORTED = 0x01,
    ERR_INVALID_CHANNEL_ID = 0x02,
    ERR_INVALID_PROTOCOL_ID = 0x03,
    ERR_NULL_PARAMETER = 0x04,
    ERR_INVALID_IOCTL_VALUE = 0x05,
    ERR_INVALID_FLAGS = 0x06,
    ERR_FAILED = 0x07,
    ERR_DEVICE_NOT_CONNECTED = 0x08,
    ERR_TIMEOUT = 0x09,
    ERR_INVALID_MSG = 0x0A,
    ERR_INVALID_TIME_INTERVAL = 0x0B,
    ERR_EXCEEDED_LIMIT = 0x0C,
    ERR_INVALID_MSG_ID = 0x0D,
    ERR_DEVICE_IN_USE = 0x0E,
    ERR_INVALID_IOCTL_ID = 0x0F,
    ERR_BUFFER_EMPTY = 0x10,
    ERR_BUFFER_FULL = 0x11,
    ERR_BUFFER_OVERFLOW = 0x12,
    ERR_PIN_INVALID = 0x13,
    ERR_CHANNEL_IN_USE = 0x14,
    ERR_MSG_PROTOCOL_ID = 0x15,
    ERR_INVALID_FILTER_ID = 0x16,
    ERR_NO_FLOW_CONTROL = 0x17,
    ERR_NOT_UNIQUE = 0x18,
    ERR_INVALID_BAUDRATE = 0x19,
    ERR_INVALID_DEVICE_ID = 0x1A,
    _,
};

pub const PASSTHRU_MSG = extern struct {
    ProtocolID: u32,
    RxStatus: u32,
    TxFlags: u32,
    Timestamp: u32,
    DataSize: u32,
    ExtraDataIndex: u32,
    Data: [4128]u8,
};

pub const SCONFIG = extern struct {
    Parameter: u32,
    Value: u32,
};

pub const SCONFIG_LIST = extern struct {
    NumOfParams: u32,
    ConfigPtr: [*]SCONFIG,
};

pub const SBYTE_ARRAY = extern struct {
    NumOfBytes: u32,
    BytePtr: [*]u8,
};

pub const PassThruOpenFn = *const fn (deviceId: ?*anyopaque, deviceIdOut: *u32) callconv(.C) u32;
pub const PassThruCloseFn = *const fn (deviceId: u32) callconv(.C) u32;
pub const PassThruConnectFn = *const fn (deviceId: u32, protocol: u32, flags: u32, baudrate: u32, channelIdOut: *u32) callconv(.C) u32;
pub const PassThruDisconnectFn = *const fn (channelId: u32) callconv(.C) u32;
pub const PassThruReadMsgsFn = *const fn (channelId: u32, msgs: [*]PASSTHRU_MSG, numMsgs: *u32, timeout: u32) callconv(.C) u32;
pub const PassThruWriteMsgsFn = *const fn (channelId: u32, msgs: [*]PASSTHRU_MSG, numMsgs: *u32, timeout: u32) callconv(.C) u32;
pub const PassThruStartMsgFilterFn = *const fn (channelId: u32, filterType: u32, maskMsg: ?*PASSTHRU_MSG, patternMsg: ?*PASSTHRU_MSG, flowControlMsg: ?*PASSTHRU_MSG, filterIdOut: *u32) callconv(.C) u32;
pub const PassThruStopMsgFilterFn = *const fn (channelId: u32, filterId: u32) callconv(.C) u32;
pub const PassThruStartPeriodicMsgFn = *const fn (channelId: u32, msg: *PASSTHRU_MSG, msgIdOut: *u32, timeInterval: u32) callconv(.C) u32;
pub const PassThruStopPeriodicMsgFn = *const fn (channelId: u32, msgId: u32) callconv(.C) u32;
pub const PassThruIoctlFn = *const fn (channelId: u32, ioctlID: u32, input: ?*anyopaque, output: ?*anyopaque) callconv(.C) u32;
pub const PassThruSetProgrammingVoltageFn = *const fn (deviceId: u32, pinNumber: u32, voltage: u32) callconv(.C) u32;
pub const PassThruReadVersionFn = *const fn (deviceId: u32, firmwareVersion: [*]u8, dllVersion: [*]u8, apiVersion: [*]u8) callconv(.C) u32;
pub const PassThruGetLastErrorFn = *const fn (errorDescription: [*]u8) callconv(.C) u32;

pub const J2534ErrorSet = error{
    NotSupported,
    InvalidChannelId,
    InvalidProtocolId,
    NullParameter,
    InvalidIoctlValue,
    InvalidFlags,
    Failed,
    DeviceNotConnected,
    Timeout,
    InvalidMsg,
    InvalidTimeInterval,
    ExceededLimit,
    InvalidMsgId,
    DeviceInUse,
    InvalidIoctlId,
    BufferEmpty,
    BufferFull,
    BufferOverflow,
    PinInvalid,
    ChannelInUse,
    MsgProtocolId,
    InvalidFilterId,
    NoFlowControl,
    NotUnique,
    InvalidBaudrate,
    InvalidDeviceId,
    UnknownError,
};

fn mapError(code: u32) J2534ErrorSet {
    const err = @as(J2534Error, @enumFromInt(code));
    return switch (err) {
        .STATUS_NOERROR => unreachable,
        .ERR_NOT_SUPPORTED => error.NotSupported,
        .ERR_INVALID_CHANNEL_ID => error.InvalidChannelId,
        .ERR_INVALID_PROTOCOL_ID => error.InvalidProtocolId,
        .ERR_NULL_PARAMETER => error.NullParameter,
        .ERR_INVALID_IOCTL_VALUE => error.InvalidIoctlValue,
        .ERR_INVALID_FLAGS => error.InvalidFlags,
        .ERR_FAILED => error.Failed,
        .ERR_DEVICE_NOT_CONNECTED => error.DeviceNotConnected,
        .ERR_TIMEOUT => error.Timeout,
        .ERR_INVALID_MSG => error.InvalidMsg,
        .ERR_INVALID_TIME_INTERVAL => error.InvalidTimeInterval,
        .ERR_EXCEEDED_LIMIT => error.ExceededLimit,
        .ERR_INVALID_MSG_ID => error.InvalidMsgId,
        .ERR_DEVICE_IN_USE => error.DeviceInUse,
        .ERR_INVALID_IOCTL_ID => error.InvalidIoctlId,
        .ERR_BUFFER_EMPTY => error.BufferEmpty,
        .ERR_BUFFER_FULL => error.BufferFull,
        .ERR_BUFFER_OVERFLOW => error.BufferOverflow,
        .ERR_PIN_INVALID => error.PinInvalid,
        .ERR_CHANNEL_IN_USE => error.ChannelInUse,
        .ERR_MSG_PROTOCOL_ID => error.MsgProtocolId,
        .ERR_INVALID_FILTER_ID => error.InvalidFilterId,
        .ERR_NO_FLOW_CONTROL => error.NoFlowControl,
        .ERR_NOT_UNIQUE => error.NotUnique,
        .ERR_INVALID_BAUDRATE => error.InvalidBaudrate,
        .ERR_INVALID_DEVICE_ID => error.InvalidDeviceId,
        _ => error.UnknownError,
    };
}

pub const J2534 = struct {
    lib: std.DynLib,
    deviceId: ?u32 = null,

    PassThruOpen: PassThruOpenFn,
    PassThruClose: PassThruCloseFn,
    PassThruConnect: PassThruConnectFn,
    PassThruDisconnect: PassThruDisconnectFn,
    PassThruReadMsgs: PassThruReadMsgsFn,
    PassThruWriteMsgs: PassThruWriteMsgsFn,
    PassThruStartMsgFilter: PassThruStartMsgFilterFn,
    PassThruStopMsgFilter: PassThruStopMsgFilterFn,
    PassThruStartPeriodicMsg: PassThruStartPeriodicMsgFn,
    PassThruStopPeriodicMsg: PassThruStopPeriodicMsgFn,
    PassThruIoctl: PassThruIoctlFn,
    PassThruSetProgrammingVoltage: PassThruSetProgrammingVoltageFn,
    PassThruReadVersion: PassThruReadVersionFn,
    PassThruGetLastError: PassThruGetLastErrorFn,

    pub fn load(dll_path: [*:0]const u8) !J2534 {
        var lib = try std.DynLib.open(std.mem.span(dll_path));

        return J2534{
            .lib = lib,
            .PassThruOpen = lib.lookup(PassThruOpenFn, "PassThruOpen") orelse return error.MissingSymbol,
            .PassThruClose = lib.lookup(PassThruCloseFn, "PassThruClose") orelse return error.MissingSymbol,
            .PassThruConnect = lib.lookup(PassThruConnectFn, "PassThruConnect") orelse return error.MissingSymbol,
            .PassThruDisconnect = lib.lookup(PassThruDisconnectFn, "PassThruDisconnect") orelse return error.MissingSymbol,
            .PassThruReadMsgs = lib.lookup(PassThruReadMsgsFn, "PassThruReadMsgs") orelse return error.MissingSymbol,
            .PassThruWriteMsgs = lib.lookup(PassThruWriteMsgsFn, "PassThruWriteMsgs") orelse return error.MissingSymbol,
            .PassThruStartMsgFilter = lib.lookup(PassThruStartMsgFilterFn, "PassThruStartMsgFilter") orelse return error.MissingSymbol,
            .PassThruStopMsgFilter = lib.lookup(PassThruStopMsgFilterFn, "PassThruStopMsgFilter") orelse return error.MissingSymbol,
            .PassThruStartPeriodicMsg = lib.lookup(PassThruStartPeriodicMsgFn, "PassThruStartPeriodicMsg") orelse return error.MissingSymbol,
            .PassThruStopPeriodicMsg = lib.lookup(PassThruStopPeriodicMsgFn, "PassThruStopPeriodicMsg") orelse return error.MissingSymbol,
            .PassThruIoctl = lib.lookup(PassThruIoctlFn, "PassThruIoctl") orelse return error.MissingSymbol,
            .PassThruSetProgrammingVoltage = lib.lookup(PassThruSetProgrammingVoltageFn, "PassThruSetProgrammingVoltage") orelse return error.MissingSymbol,
            .PassThruReadVersion = lib.lookup(PassThruReadVersionFn, "PassThruReadVersion") orelse return error.MissingSymbol,
            .PassThruGetLastError = lib.lookup(PassThruGetLastErrorFn, "PassThruGetLastError") orelse return error.MissingSymbol,
        };
    }

    pub fn unload(self: *J2534) void {
        self.lib.close();
    }

    pub fn open(self: *J2534) !void {
        var deviceId: u32 = 0;
        const res = self.PassThruOpen(null, &deviceId);
        if (res != @intFromEnum(J2534Error.STATUS_NOERROR)) return mapError(res);
        self.deviceId = deviceId;
    }

    pub fn close(self: *J2534) !void {
        if (self.deviceId) |deviceId| {
            const res = self.PassThruClose(deviceId);
            if (res != @intFromEnum(J2534Error.STATUS_NOERROR)) return mapError(res);
            self.deviceId = null;
        }
    }

    pub fn connect(self: *J2534, protocol: Protocol, flags: u32, baudrate: u32) !u32 {
        var channelId: u32 = 0;
        const res = self.PassThruConnect(self.deviceId orelse return error.DeviceNotConnected, @intFromEnum(protocol), flags, baudrate, &channelId);
        if (res != @intFromEnum(J2534Error.STATUS_NOERROR)) return mapError(res);
        return channelId;
    }

    pub fn disconnect(self: *J2534, channelId: u32) !void {
        const res = self.PassThruDisconnect(channelId);
        if (res != @intFromEnum(J2534Error.STATUS_NOERROR)) return mapError(res);
    }

    pub fn getLastError(self: *J2534, buffer: [*]u8) !void {
        const res = self.PassThruGetLastError(buffer);
        if (res != @intFromEnum(J2534Error.STATUS_NOERROR)) return mapError(res);
    }
};
