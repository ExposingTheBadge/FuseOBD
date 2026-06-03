const std = @import("std");
const j2534 = @import("j2534.zig");

// Note: To pass strings from Python properly, they should be null-terminated C strings.
// Using Zig's callconv(.C) enables proper interop.
export fn fuse_j2534_open(dll_path: [*:0]const u8) callconv(.C) i32 {
    // Normally we'd load the DLL dynamically and allocate a handle structure.
    // For this stub, we return -1 indicating not fully implemented here yet.
    _ = dll_path;
    return -1;
}

export fn fuse_j2534_close(handle: i32) callconv(.C) i32 {
    _ = handle;
    return 0;
}

export fn fuse_j2534_connect(handle: i32, protocol: u32, flags: u32, baudrate: u32) callconv(.C) i32 {
    _ = handle;
    _ = protocol;
    _ = flags;
    _ = baudrate;
    return -1;
}

export fn fuse_j2534_disconnect(handle: i32, channel_id: u32) callconv(.C) i32 {
    _ = handle;
    _ = channel_id;
    return 0;
}

export fn fuse_j2534_read_msgs(handle: i32, channel_id: u32, msg_buf: [*]j2534.PASSTHRU_MSG, num_msgs: *u32, timeout: u32) callconv(.C) i32 {
    _ = handle;
    _ = channel_id;
    _ = msg_buf;
    _ = num_msgs;
    _ = timeout;
    return 0;
}

export fn fuse_j2534_write_msgs(handle: i32, channel_id: u32, msg_buf: [*]j2534.PASSTHRU_MSG, num_msgs: *u32, timeout: u32) callconv(.C) i32 {
    _ = handle;
    _ = channel_id;
    _ = msg_buf;
    _ = num_msgs;
    _ = timeout;
    return 0;
}

export fn fuse_j2534_read_battery_voltage(handle: i32, voltage_mv: *u32) callconv(.C) i32 {
    _ = handle;
    _ = voltage_mv;
    return 0;
}

export fn fuse_j2534_read_version(handle: i32, fw: [*]u8, dll: [*]u8, api: [*]u8) callconv(.C) i32 {
    _ = handle;
    _ = fw;
    _ = dll;
    _ = api;
    return 0;
}

export fn fuse_j2534_get_last_error(handle: i32, buf: [*]u8) callconv(.C) i32 {
    _ = handle;
    _ = buf;
    return 0;
}
