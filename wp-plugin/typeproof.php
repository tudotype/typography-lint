<?php
/**
 * Plugin Name: Typeproof
 * Plugin URI:  https://github.com/tudotype/typeproof
 * Description: Language-aware typographic correction for WordPress. Fixes quotes, dashes, spacing, diacritics, and 50+ Unicode-level rules across 20+ languages.
 * Version:     0.1.0
 * Author:      João Miranda / Automattic
 * Author URI:  https://automattic.design
 * License:     GPL-2.0-or-later
 * Text Domain: typeproof
 * Requires at least: 6.0
 * Requires PHP: 7.4
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'TI_VERSION', '0.1.0' );
define( 'TI_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'TI_PLUGIN_URL', plugin_dir_url( __FILE__ ) );

/**
 * Load plugin classes.
 */
function ti_load() {
	require_once TI_PLUGIN_DIR . 'includes/class-ti-linter.php';
	require_once TI_PLUGIN_DIR . 'includes/class-ti-rest-controller.php';
	require_once TI_PLUGIN_DIR . 'includes/class-ti-settings.php';
	require_once TI_PLUGIN_DIR . 'includes/class-ti-content-filter.php';
}
add_action( 'plugins_loaded', 'ti_load' );

/**
 * Register REST routes.
 */
function ti_rest_init() {
	$controller = new TI_REST_Controller();
	$controller->register_routes();
}
add_action( 'rest_api_init', 'ti_rest_init' );

/**
 * Disable wptexturize if configured.
 *
 * WP's built-in texturize does basic quote/dash substitution that
 * conflicts with our language-aware rules.
 */
function ti_maybe_disable_wptexturize() {
	if ( get_option( 'ti_disable_wptexturize', true ) ) {
		remove_filter( 'the_content', 'wptexturize' );
		remove_filter( 'the_title', 'wptexturize' );
		remove_filter( 'the_excerpt', 'wptexturize' );
		remove_filter( 'widget_text_content', 'wptexturize' );
		remove_filter( 'comment_text', 'wptexturize' );
	}
}
add_action( 'init', 'ti_maybe_disable_wptexturize' );

/**
 * Enqueue block editor sidebar script.
 */
function ti_enqueue_block_editor_assets() {
	wp_enqueue_script(
		'ti-sidebar',
		TI_PLUGIN_URL . 'assets/js/ti-sidebar.js',
		array( 'wp-plugins', 'wp-edit-post', 'wp-element', 'wp-components', 'wp-data', 'wp-api-fetch', 'wp-i18n' ),
		TI_VERSION,
		true
	);

	wp_localize_script( 'ti-sidebar', 'tiSettings', array(
		'restUrl'  => rest_url( 'typeproof/v1/' ),
		'nonce'    => wp_create_nonce( 'wp_rest' ),
		'language' => TI_Linter::get_configured_language(),
	) );

	wp_enqueue_style(
		'ti-sidebar',
		TI_PLUGIN_URL . 'assets/css/ti-admin.css',
		array(),
		TI_VERSION
	);
}
add_action( 'enqueue_block_editor_assets', 'ti_enqueue_block_editor_assets' );

/**
 * Register settings on admin_init.
 */
function ti_admin_init() {
	if ( class_exists( 'TI_Settings' ) ) {
		TI_Settings::register();
	}
}
add_action( 'admin_init', 'ti_admin_init' );

/**
 * Add settings page to admin menu.
 */
function ti_admin_menu() {
	add_options_page(
		__( 'Typeproof', 'typeproof' ),
		__( 'Typeproof', 'typeproof' ),
		'manage_options',
		'typeproof',
		array( 'TI_Settings', 'render_page' )
	);
}
add_action( 'admin_menu', 'ti_admin_menu' );

/**
 * Hook content filter if auto-correct is enabled.
 */
function ti_maybe_hook_content_filter() {
	if ( get_option( 'ti_auto_correct', false ) ) {
		TI_Content_Filter::init();
	}
}
add_action( 'init', 'ti_maybe_hook_content_filter' );

/**
 * Set default options on activation.
 */
function ti_activate() {
	add_option( 'ti_python_path', 'python3' );
	add_option( 'ti_linter_path', '' );
	add_option( 'ti_language', 'auto' );
	add_option( 'ti_register', '' );
	add_option( 'ti_auto_correct', false );
	add_option( 'ti_disable_wptexturize', true );
}
register_activation_hook( __FILE__, 'ti_activate' );
