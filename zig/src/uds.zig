const std = @import("std");
const j2534 = @import("j2534.zig");

pub const UDSService = enum(u8) {
    DIAGNOSTIC_SESSION_CONTROL = 0x10,
    ECU_RESET = 0x11,
    CLEAR_DTC = 0x14,
    READ_DTC_INFO = 0x19,
    READ_DATA_BY_ID = 0x22,
    READ_MEMORY_BY_ADDRESS = 0x23,
    SECURITY_ACCESS = 0x27,
    COMMUNICATION_CONTROL = 0x28,
    WRITE_DATA_BY_ID = 0x2E,
    IO_CONTROL = 0x2F,
    ROUTINE_CONTROL = 0x31,
    REQUEST_DOWNLOAD = 0x34,
    TRANSFER_DATA = 0x36,
    REQUEST_TRANSFER_EXIT = 0x37,
    TESTER_PRESENT = 0x3E,
    _,
};

pub const UDSSession = enum(u8) {
    DEFAULT = 0x01,
    PROGRAMMING = 0x02,
    EXTENDED = 0x03,
    FORD_DIAG = 0x85,
    _,
};

pub const DTCSubFunction = enum(u8) {
    REPORT_NUMBER_BY_STATUS = 0x01,
    REPORT_BY_STATUS = 0x02,
    REPORT_SNAPSHOT_ID = 0x03,
    REPORT_SNAPSHOT_BY_DTC = 0x04,
    REPORT_STORED_DATA = 0x06,
    REPORT_PENDING = 0x07,
    REPORT_CONFIRMED = 0x0A,
    REPORT_SUPPORTED_DTC = 0x0F,
    _,
};

pub const NRC = enum(u8) {
    GENERAL_REJECT = 0x10,
    SERVICE_NOT_SUPPORTED = 0x11,
    SUBFUNCTION_NOT_SUPPORTED = 0x12,
    INCORRECT_LENGTH = 0x13,
    RESPONSE_TOO_LONG = 0x14,
    BUSY_REPEAT = 0x21,
    CONDITIONS_NOT_CORRECT = 0x22,
    REQUEST_SEQUENCE_ERROR = 0x24,
    REQUEST_OUT_OF_RANGE = 0x31,
    SECURITY_ACCESS_DENIED = 0x33,
    INVALID_KEY = 0x35,
    EXCEEDED_ATTEMPTS = 0x36,
    TIME_DELAY_NOT_EXPIRED = 0x37,
    UPLOAD_DOWNLOAD_NOT_ACCEPTED = 0x70,
    TRANSFER_SUSPENDED = 0x71,
    GENERAL_PROGRAMMING_FAILURE = 0x72,
    RESPONSE_PENDING = 0x78,
    SUBFUNCTION_NOT_SUPPORTED_IN_SESSION = 0x7E,
    SERVICE_NOT_SUPPORTED_IN_SESSION = 0x7F,
    _,
};

pub const UDSClient = struct {
    j2534_inst: *j2534.J2534,
    channel_id: u32,
    tx_id: u32,
    rx_id: u32,
    protocol: j2534.Protocol,
    filter_id: ?u32 = null,

    pub fn init(j2534_inst: *j2534.J2534, channel_id: u32, tx_id: u32, rx_id: u32, protocol: j2534.Protocol) UDSClient {
        return .{
            .j2534_inst = j2534_inst,
            .channel_id = channel_id,
            .tx_id = tx_id,
            .rx_id = rx_id,
            .protocol = protocol,
        };
    }

    pub fn connect(self: *UDSClient) !void {
        if (self.protocol != .ISO15765) return error.UnsupportedProtocol;
        
        var mask_msg: j2534.PASSTHRU_MSG = undefined;
        var pattern_msg: j2534.PASSTHRU_MSG = undefined;
        var flow_msg: j2534.PASSTHRU_MSG = undefined;

        @memset(std.mem.asBytes(&mask_msg), 0);
        @memset(std.mem.asBytes(&pattern_msg), 0);
        @memset(std.mem.asBytes(&flow_msg), 0);

        mask_msg.ProtocolID = @intFromEnum(self.protocol);
        mask_msg.DataSize = 4;
        mask_msg.Data[0] = 0xFF;
        mask_msg.Data[1] = 0xFF;
        mask_msg.Data[2] = 0xFF;
        mask_msg.Data[3] = 0xFF;

        pattern_msg.ProtocolID = @intFromEnum(self.protocol);
        pattern_msg.DataSize = 4;
        pattern_msg.Data[0] = @intCast((self.rx_id >> 24) & 0xFF);
        pattern_msg.Data[1] = @intCast((self.rx_id >> 16) & 0xFF);
        pattern_msg.Data[2] = @intCast((self.rx_id >> 8) & 0xFF);
        pattern_msg.Data[3] = @intCast(self.rx_id & 0xFF);

        flow_msg.ProtocolID = @intFromEnum(self.protocol);
        flow_msg.DataSize = 4;
        flow_msg.Data[0] = @intCast((self.tx_id >> 24) & 0xFF);
        flow_msg.Data[1] = @intCast((self.tx_id >> 16) & 0xFF);
        flow_msg.Data[2] = @intCast((self.tx_id >> 8) & 0xFF);
        flow_msg.Data[3] = @intCast(self.tx_id & 0xFF);

        self.filter_id = try self.j2534_inst.startMsgFilter(self.channel_id, .FLOW_CONTROL, &mask_msg, &pattern_msg, &flow_msg);
    }

    pub fn disconnect(self: *UDSClient) !void {
        if (self.filter_id) |fid| {
            try self.j2534_inst.stopMsgFilter(self.channel_id, fid);
            self.filter_id = null;
        }
    }

    pub fn request(self: *UDSClient, req_data: []const u8, resp_buffer: []u8) !usize {
        var tx_msg: j2534.PASSTHRU_MSG = undefined;
        @memset(std.mem.asBytes(&tx_msg), 0);
        
        tx_msg.ProtocolID = @intFromEnum(self.protocol);
        tx_msg.DataSize = @as(u32, @intCast(4 + req_data.len));
        tx_msg.Data[0] = @intCast((self.tx_id >> 24) & 0xFF);
        tx_msg.Data[1] = @intCast((self.tx_id >> 16) & 0xFF);
        tx_msg.Data[2] = @intCast((self.tx_id >> 8) & 0xFF);
        tx_msg.Data[3] = @intCast(self.tx_id & 0xFF);
        
        @memcpy(tx_msg.Data[4..4 + req_data.len], req_data);

        var num_msgs: u32 = 1;
        try self.j2534_inst.writeMsgs(self.channel_id, @ptrCast(&tx_msg), &num_msgs, 1000);

        var rx_msg: j2534.PASSTHRU_MSG = undefined;
        while (true) {
            num_msgs = 1;
            @memset(std.mem.asBytes(&rx_msg), 0);
            
            self.j2534_inst.readMsgs(self.channel_id, @ptrCast(&rx_msg), &num_msgs, 1000) catch |err| switch (err) {
                error.Timeout => return error.Timeout,
                else => return err,
            };

            if (num_msgs == 1 and rx_msg.DataSize >= 5) {
                const payload = rx_msg.Data[4..rx_msg.DataSize];
                
                if (payload[0] == 0x7F) {
                    if (payload.len >= 3) {
                        const nrc = payload[2];
                        if (nrc == @intFromEnum(NRC.RESPONSE_PENDING)) {
                            continue;
                        }
                        return error.NegativeResponse;
                    }
                }
                
                const copy_len = @min(payload.len, resp_buffer.len);
                @memcpy(resp_buffer[0..copy_len], payload[0..copy_len]);
                return copy_len;
            }
        }
    }

    pub fn diagnosticSession(self: *UDSClient, session: UDSSession) !void {
        const req = [_]u8{ @intFromEnum(UDSService.DIAGNOSTIC_SESSION_CONTROL), @intFromEnum(session) };
        var resp: [64]u8 = undefined;
        _ = try self.request(&req, &resp);
    }

    pub fn testerPresent(self: *UDSClient) !void {
        const req = [_]u8{ @intFromEnum(UDSService.TESTER_PRESENT), 0x80 }; // 0x80 = suppress positive response
        var resp: [64]u8 = undefined;
        _ = self.request(&req, &resp) catch |err| switch (err) {
            error.Timeout => return, // Timeout is expected if response is suppressed
            else => return err,
        };
    }

    pub fn ecuReset(self: *UDSClient, reset_type: u8) !void {
        const req = [_]u8{ @intFromEnum(UDSService.ECU_RESET), reset_type };
        var resp: [64]u8 = undefined;
        _ = try self.request(&req, &resp);
    }

    pub fn readDataById(self: *UDSClient, did: u16, out_buffer: []u8) !usize {
        const req = [_]u8{ 
            @intFromEnum(UDSService.READ_DATA_BY_ID), 
            @intCast((did >> 8) & 0xFF), 
            @intCast(did & 0xFF) 
        };
        var resp: [1024]u8 = undefined;
        const len = try self.request(&req, &resp);
        if (len < 3) return error.InvalidResponse;
        
        const data_len = len - 3;
        const copy_len = @min(data_len, out_buffer.len);
        @memcpy(out_buffer[0..copy_len], resp[3..3 + copy_len]);
        return copy_len;
    }

    pub fn writeDataById(self: *UDSClient, did: u16, data: []const u8) !void {
        var req: [1024]u8 = undefined;
        req[0] = @intFromEnum(UDSService.WRITE_DATA_BY_ID);
        req[1] = @intCast((did >> 8) & 0xFF);
        req[2] = @intCast(did & 0xFF);
        @memcpy(req[3..3 + data.len], data);
        
        var resp: [64]u8 = undefined;
        _ = try self.request(req[0..3 + data.len], &resp);
    }

    pub fn securityAccessSeed(self: *UDSClient, level: u8, out_seed: []u8) !usize {
        const req = [_]u8{ @intFromEnum(UDSService.SECURITY_ACCESS), level };
        var resp: [64]u8 = undefined;
        const len = try self.request(&req, &resp);
        if (len < 2) return error.InvalidResponse;
        
        const seed_len = len - 2;
        const copy_len = @min(seed_len, out_seed.len);
        @memcpy(out_seed[0..copy_len], resp[2..2 + copy_len]);
        return copy_len;
    }

    pub fn securityAccessKey(self: *UDSClient, level: u8, key: []const u8) !void {
        var req: [64]u8 = undefined;
        req[0] = @intFromEnum(UDSService.SECURITY_ACCESS);
        req[1] = level;
        @memcpy(req[2..2 + key.len], key);
        
        var resp: [64]u8 = undefined;
        _ = try self.request(req[0..2 + key.len], &resp);
    }

    pub fn clearDtc(self: *UDSClient, group: u32) !void {
        const req = [_]u8{
            @intFromEnum(UDSService.CLEAR_DTC),
            @intCast((group >> 16) & 0xFF),
            @intCast((group >> 8) & 0xFF),
            @intCast(group & 0xFF)
        };
        var resp: [64]u8 = undefined;
        _ = try self.request(&req, &resp);
    }

    pub fn readDtc(self: *UDSClient, subfunc: u8, mask: u8, out_buffer: []u8) !usize {
        const req = [_]u8{ @intFromEnum(UDSService.READ_DTC_INFO), subfunc, mask };
        var resp: [1024]u8 = undefined;
        const len = try self.request(&req, &resp);
        const copy_len = @min(len, out_buffer.len);
        @memcpy(out_buffer[0..copy_len], resp[0..copy_len]);
        return copy_len;
    }

    pub fn routineControl(self: *UDSClient, control_type: u8, routine_id: u16, data: []const u8, out_buffer: []u8) !usize {
        var req: [1024]u8 = undefined;
        req[0] = @intFromEnum(UDSService.ROUTINE_CONTROL);
        req[1] = control_type;
        req[2] = @intCast((routine_id >> 8) & 0xFF);
        req[3] = @intCast(routine_id & 0xFF);
        @memcpy(req[4..4 + data.len], data);
        
        var resp: [1024]u8 = undefined;
        const len = try self.request(req[0..4 + data.len], &resp);
        const copy_len = @min(len, out_buffer.len);
        @memcpy(out_buffer[0..copy_len], resp[0..copy_len]);
        return copy_len;
    }

    pub fn ioControl(self: *UDSClient, did: u16, control_param: u8, state: []const u8) !void {
        var req: [64]u8 = undefined;
        req[0] = @intFromEnum(UDSService.IO_CONTROL);
        req[1] = @intCast((did >> 8) & 0xFF);
        req[2] = @intCast(did & 0xFF);
        req[3] = control_param;
        @memcpy(req[4..4 + state.len], state);
        
        var resp: [64]u8 = undefined;
        _ = try self.request(req[0..4 + state.len], &resp);
    }
};
