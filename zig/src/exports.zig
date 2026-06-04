const std = @import("std");
const j2534 = @import("j2534.zig");
const uds = @import("uds.zig");

// Maintain a global array of devices (handles 0 to 15)
var devices: [16]?j2534.J2534 = .{null} ** 16;
var devices_lock = std.Thread.Mutex{};

fn getDevice(handle: i32) ?*j2534.J2534 {
    if (handle < 0 or handle >= 16) return null;
    if (devices[@as(usize, @intCast(handle))]) |*d| return d;
    return null;
}

export fn fuse_j2534_open(dll_path: [*:0]const u8) callconv(.C) i32 {
    devices_lock.lock();
    defer devices_lock.unlock();

    var handle: i32 = -1;
    for (&devices, 0..) |*slot, i| {
        if (slot.* == null) {
            handle = @intCast(i);
            break;
        }
    }
    if (handle == -1) return -1; // Max devices reached

    var dev = j2534.J2534.load(dll_path) catch return -1;
    dev.open() catch {
        dev.unload();
        return -1;
    };

    devices[@as(usize, @intCast(handle))] = dev;
    return handle;
}

export fn fuse_j2534_close(handle: i32) callconv(.C) i32 {
    devices_lock.lock();
    defer devices_lock.unlock();

    if (handle < 0 or handle >= 16) return -1;
    const idx = @as(usize, @intCast(handle));
    if (devices[idx]) |*dev| {
        dev.close() catch {};
        dev.unload();
        devices[idx] = null;
        return 0;
    }
    return -1;
}

export fn fuse_j2534_connect(handle: i32, protocol: u32, flags: u32, baudrate: u32) callconv(.C) i32 {
    const dev = getDevice(handle) orelse return -1;
    const p = @as(j2534.Protocol, @enumFromInt(protocol));
    const channelId = dev.connect(p, flags, baudrate) catch return -1;
    return @as(i32, @bitCast(channelId));
}

export fn fuse_j2534_disconnect(handle: i32, channel_id: u32) callconv(.C) i32 {
    const dev = getDevice(handle) orelse return -1;
    dev.disconnect(channel_id) catch return -1;
    return 0;
}

export fn fuse_j2534_read_msgs(handle: i32, channel_id: u32, msg_buf: [*]j2534.PASSTHRU_MSG, num_msgs: *u32, timeout: u32) callconv(.C) i32 {
    const dev = getDevice(handle) orelse return -1;
    dev.readMsgs(channel_id, msg_buf, num_msgs, timeout) catch return -1;
    return 0;
}

export fn fuse_j2534_write_msgs(handle: i32, channel_id: u32, msg_buf: [*]j2534.PASSTHRU_MSG, num_msgs: *u32, timeout: u32) callconv(.C) i32 {
    const dev = getDevice(handle) orelse return -1;
    dev.writeMsgs(channel_id, msg_buf, num_msgs, timeout) catch return -1;
    return 0;
}

export fn fuse_j2534_read_battery_voltage(handle: i32, voltage_mv: *u32) callconv(.C) i32 {
    const dev = getDevice(handle) orelse return -1;
    voltage_mv.* = dev.readBatteryVoltage() catch return -1;
    return 0;
}

export fn fuse_j2534_read_version(handle: i32, fw: [*]u8, dll: [*]u8, api: [*]u8) callconv(.C) i32 {
    const dev = getDevice(handle) orelse return -1;
    dev.readVersion(fw, dll, api) catch return -1;
    return 0;
}

export fn fuse_j2534_get_last_error(handle: i32, buf: [*]u8) callconv(.C) i32 {
    const dev = getDevice(handle) orelse return -1;
    dev.getLastError(buf) catch return -1;
    return 0;
}

// -----------------------------------------------------------------------------
// UDS Client Exports
// -----------------------------------------------------------------------------

var uds_clients: [16]?uds.UDSClient = .{null} ** 16;
var uds_lock = std.Thread.Mutex{};

fn getUdsClient(handle: i32) ?*uds.UDSClient {
    if (handle < 0 or handle >= 16) return null;
    if (uds_clients[@as(usize, @intCast(handle))]) |*c| return c;
    return null;
}

export fn fuse_uds_init(j2534_handle: i32, channel_id: u32, tx_id: u32, rx_id: u32, protocol: u32) callconv(.C) i32 {
    const dev = getDevice(j2534_handle) orelse return -1;
    const p = @as(j2534.Protocol, @enumFromInt(protocol));

    uds_lock.lock();
    defer uds_lock.unlock();

    var handle: i32 = -1;
    for (&uds_clients, 0..) |*slot, i| {
        if (slot.* == null) {
            handle = @intCast(i);
            break;
        }
    }
    if (handle == -1) return -1;

    uds_clients[@as(usize, @intCast(handle))] = uds.UDSClient.init(dev, channel_id, tx_id, rx_id, p);
    return handle;
}

export fn fuse_uds_free(handle: i32) callconv(.C) i32 {
    uds_lock.lock();
    defer uds_lock.unlock();

    if (handle < 0 or handle >= 16) return -1;
    const idx = @as(usize, @intCast(handle));
    if (uds_clients[idx]) |*client| {
        client.disconnect() catch {};
        uds_clients[idx] = null;
        return 0;
    }
    return -1;
}

export fn fuse_uds_connect(handle: i32) callconv(.C) i32 {
    const client = getUdsClient(handle) orelse return -1;
    client.connect() catch return -1;
    return 0;
}

export fn fuse_uds_disconnect(handle: i32) callconv(.C) i32 {
    const client = getUdsClient(handle) orelse return -1;
    client.disconnect() catch return -1;
    return 0;
}

export fn fuse_uds_request(handle: i32, req_data: [*]const u8, req_len: u32, resp_data: [*]u8, resp_max_len: u32) callconv(.C) i32 {
    const client = getUdsClient(handle) orelse return -1;
    const size = client.request(req_data[0..req_len], resp_data[0..resp_max_len]) catch return -1;
    return @intCast(size);
}

