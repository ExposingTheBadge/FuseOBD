const std = @import("std");
const j2534 = @import("j2534.zig");

pub const FordNetwork = enum(u8) {
    HS_CAN = 1,
    MS_CAN = 2,
    HS_CAN_EXT = 3,
    ISO = 4,
    SCP = 5,
};

pub const NetworkConfig = struct {
    name: []const u8,
    network: FordNetwork,
    protocol: j2534.Protocol,
    baudrate: u32,
    flags: u32 = 0,
    tx_id: u32 = 0x7E0,
    rx_id: u32 = 0x7E8,
    obd_tx: u32 = 0x7DF,
    can_id_bits: u8 = 11,
};

pub const FORD_HS_CAN = NetworkConfig{
    .name = "Ford HS CAN",
    .network = .HS_CAN,
    .protocol = .ISO15765,
    .baudrate = 500000,
};

pub const FORD_MS_CAN = NetworkConfig{
    .name = "Ford MS CAN",
    .network = .MS_CAN,
    .protocol = .ISO15765,
    .baudrate = 125000,
};

pub const FORD_HS_CAN_29BIT = NetworkConfig{
    .name = "Ford HS CAN 29-bit",
    .network = .HS_CAN_EXT,
    .protocol = .ISO15765,
    .baudrate = 500000,
    .flags = j2534.ConnectFlag.CAN_29BIT_ID_MASK,
    .tx_id = 0x18DA00FF,
    .rx_id = 0x18DAFFEE,
    .obd_tx = 0x18DB33F1,
    .can_id_bits = 29,
};

pub const FordModule = struct {
    name: []const u8,
    abbreviation: []const u8,
    address: u8,
    network: FordNetwork,
    description: []const u8 = "",
    verified: bool = false,

    pub fn tx_id(self: FordModule) u32 {
        return 0x700 + @as(u32, self.address);
    }

    pub fn rx_id(self: FordModule) u32 {
        return 0x700 + @as(u32, self.address) + 8;
    }
};

pub const FORD_MODULES = [_]FordModule{
    // Powertrain
    .{ .name = "Powertrain Control Module", .abbreviation = "PCM", .address = 0xE0, .network = .HS_CAN, .verified = true },
    .{ .name = "Transmission Control Module", .abbreviation = "TCM", .address = 0xE1, .network = .HS_CAN, .verified = true },
    // Chassis / safety
    .{ .name = "Anti-Lock Brake System", .abbreviation = "ABS", .address = 0x20, .network = .HS_CAN, .verified = true },
    .{ .name = "Restraint Control Module", .abbreviation = "RCM", .address = 0x26, .network = .HS_CAN, .verified = true },
    .{ .name = "Power Steering Control Module", .abbreviation = "PSCM", .address = 0x30, .network = .HS_CAN, .verified = true },
    .{ .name = "Electric Power Steering", .abbreviation = "EPAS", .address = 0x62, .network = .HS_CAN, .verified = false },
    // Body / convenience
    .{ .name = "Instrument Panel Cluster", .abbreviation = "IPC", .address = 0x20, .network = .MS_CAN, .verified = true },
    .{ .name = "Body Control Module", .abbreviation = "BCM", .address = 0x26, .network = .MS_CAN, .verified = true },
    .{ .name = "Steering Column Control Module", .abbreviation = "SCCM", .address = 0x24, .network = .MS_CAN, .verified = true },
    .{ .name = "Audio Control Module", .abbreviation = "ACM", .address = 0x27, .network = .MS_CAN, .verified = true },
    .{ .name = "Front Controls Interface Module", .abbreviation = "FCIM", .address = 0xC4, .network = .MS_CAN, .verified = true, .description = "Climate-control faceplate" },
    .{ .name = "Driver Door Module", .abbreviation = "DDM", .address = 0x31, .network = .MS_CAN, .verified = true },
    .{ .name = "Passenger Door Module", .abbreviation = "PDM", .address = 0x32, .network = .MS_CAN, .verified = true },
    .{ .name = "Driver Seat Module", .abbreviation = "DSM", .address = 0x40, .network = .MS_CAN, .verified = true, .description = "Power-seat memory; previously listed as SCMD" },
    // Network gateway
    .{ .name = "Gateway Module A", .abbreviation = "GWM", .address = 0x60, .network = .HS_CAN, .verified = true },
    // SYNC / infotainment
    .{ .name = "SYNC / APIM", .abbreviation = "APIM", .address = 0xC0, .network = .HS_CAN, .verified = true },
};
