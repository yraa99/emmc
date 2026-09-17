cmake_minimum_required(VERSION 3.17)

include(pico_sdk_import.cmake)
project(emmc_reader_writer C CXX ASM)

pico_sdk_init()

add_executable(emmc_reader_writer
    src/main.c
    src/usb_descriptors.c
    src/proto_emmc.c
)

pico_enable_stdio_usb(emmc_reader_writer 1)
pico_enable_stdio_uart(emmc_reader_writer 0)

pico_generate_pio_header(emmc_reader_writer ${CMAKE_CURRENT_LIST_DIR}/src/emmc_dat0_rx.pio)

# Path include untuk src dan struktur direktori TinyUSB SDK
target_include_directories(emmc_reader_writer PUBLIC
    src
    ${PICO_SDK_PATH}/lib/tinyusb/src
    ${PICO_SDK_PATH}/lib/tinyusb/hw
)

target_link_libraries(emmc_reader_writer PUBLIC
    pico_stdlib
    hardware_spi
    hardware_pio
    hardware_dma
    hardware_pwm
    tinyusb_device
    tinyusb_board
)

pico_add_extra_outputs(emmc_reader_writer)